"""Incremental reindex use case."""
from __future__ import annotations

import dataclasses
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from codegraph.application.partition_planner import IndexPartition, plan_partitions
from codegraph.domain.config import CodegraphConfig
from codegraph.domain.index_progress import ProgressState
from codegraph.domain.models import Symbol, Edge, Chunk
from codegraph.domain.workspace import IndexMetadata


@dataclass
class ReindexProcessedFile:
    file_path: str
    symbols: list[Symbol]
    edges: list[Edge]
    chunks: list[Chunk]
    failed: bool = False
    error: str | None = None


class IncrementalReindexUseCase:
    """Reindexes only changed files since last index."""

    def __init__(
        self,
        store,  # SymbolStore protocol
        parser,  # TreeSitterParser
        git_client,  # GitClient protocol
        embedding_provider=None,  # EmbeddingProvider protocol (optional)
        chunker=None,  # CodeChunker (optional)
        progress_tracker=None,
        config: Optional[CodegraphConfig] = None,
    ) -> None:
        self._store = store
        self._parser = parser
        self._git = git_client
        self._embedder = embedding_provider
        self._chunker = chunker
        self._progress_tracker = progress_tracker
        self._config = config or CodegraphConfig()

    def execute(self, repo_root: str) -> ReindexResult:
        """Run incremental reindex on changed files only."""
        start = time.time()
        result = ReindexResult()

        metadata = self._store.get_metadata()
        if metadata is None:
            result.needs_full_index = True
            return result

        generation = metadata.generation + 1
        changed = self._get_changed_files(metadata)
        result.files_changed = len(changed)

        if not changed:
            result.duration = time.time() - start
            return result

        deleted_files = [f["file_path"] for f in changed if f.get("status") == "deleted"]
        modified_files = [f["file_path"] for f in changed if f.get("status") != "deleted"]

        try:
            for fp in deleted_files:
                self._store.delete_symbols_by_file(fp)
                self._store.delete_edges_by_file(fp)
                self._store.delete_chunks_by_file(fp)
                result.files_deleted += 1

            submodules: list[str] = []
            if self._git and hasattr(self._git, "list_submodule_paths"):
                submodules = self._git.list_submodule_paths()
            min_partition_files = getattr(self._config.index, "min_partition_files", 1)
            partitions = plan_partitions(
                files=modified_files,
                submodules=submodules,
                min_partition_files=min_partition_files,
            )

            operation_id: str | None = None
            if self._progress_tracker is not None:
                operation_id = self._progress_tracker.start(
                    mode="reindex",
                    partitions_total=len(partitions),
                    files_total=len(modified_files),
                )
                self._progress_tracker.register_partitions(
                    operation_id,
                    {p.root_path: len(p.files) for p in partitions},
                )
                self._progress_tracker.set_state(operation_id, ProgressState.RUNNING)
                result.operation_id = operation_id

            processed = self._process_partitions(
                repo_root=repo_root,
                partitions=partitions,
                generation=generation,
                operation_id=operation_id,
            )

            all_symbols: list[Symbol] = []
            all_edges: list[Edge] = []
            all_chunks: list[Chunk] = []
            for item in processed:
                if item.failed:
                    result.files_failed += 1
                    continue
                all_symbols.extend(item.symbols)
                all_edges.extend(item.edges)
                all_chunks.extend(item.chunks)
                result.files_reindexed += 1

            if self._progress_tracker is not None and operation_id:
                self._progress_tracker.set_state(operation_id, ProgressState.COMMITTING)

            if all_symbols:
                self._store.upsert_symbols(all_symbols)
            if all_edges:
                self._store.upsert_edges(all_edges)
            if all_chunks:
                self._store.upsert_chunks(all_chunks)

            if self._embedder and all_chunks:
                try:
                    texts = [c.embedding_text or c.content for c in all_chunks]
                    vectors = self._embedder.embed_batch(texts)
                    for i, chunk in enumerate(all_chunks):
                        if i < len(vectors):
                            chunk.vector = vectors[i]
                            chunk.has_vector = True
                    self._store.upsert_chunks(all_chunks)
                except Exception:
                    result.embedding_errors += 1

            head_commit = self._git.get_head_commit() if self._git else None
            metadata.generation = generation
            if head_commit:
                metadata.workspace_state.head_commit = head_commit
            self._store.set_metadata(metadata)

            result.symbols_count = len(all_symbols)
            result.edges_count = len(all_edges)
            result.generation = generation
            result.duration = time.time() - start

            if self._progress_tracker is not None and operation_id:
                self._progress_tracker.complete(operation_id)

            return result
        except Exception as exc:
            if self._progress_tracker is not None and operation_id:
                self._progress_tracker.fail(operation_id, str(exc))
            raise

    def _process_partitions(
        self,
        repo_root: str,
        partitions: list[IndexPartition],
        generation: int,
        operation_id: str | None,
    ) -> list[ReindexProcessedFile]:
        workers = max(1, getattr(self._config.index, "parallel_workers", 1))
        if workers == 1 or len(partitions) <= 1:
            out: list[ReindexProcessedFile] = []
            for p in partitions:
                out.extend(self._process_partition(repo_root, p, generation, operation_id))
            return out

        out: list[ReindexProcessedFile] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._process_partition, repo_root, p, generation, operation_id)
                for p in partitions
            ]
            for future in as_completed(futures):
                out.extend(future.result())
        return out

    def _process_partition(
        self,
        repo_root: str,
        partition: IndexPartition,
        generation: int,
        operation_id: str | None,
    ) -> list[ReindexProcessedFile]:
        if self._progress_tracker is not None and operation_id:
            self._progress_tracker.mark_partition_started(operation_id, partition.root_path)

        out: list[ReindexProcessedFile] = []
        for file_path in partition.files:
            if self._progress_tracker is not None and operation_id:
                self._progress_tracker.mark_file_started(operation_id, file_path)

            self._store.delete_symbols_by_file(file_path)
            self._store.delete_edges_by_file(file_path)
            self._store.delete_chunks_by_file(file_path)

            processed = self._process_file(repo_root, file_path, generation)
            if self._progress_tracker is not None and operation_id:
                if processed.failed:
                    self._progress_tracker.mark_file_failed(
                        operation_id,
                        processed.error or "failed to process file",
                        partition=partition.root_path,
                    )
                else:
                    self._progress_tracker.mark_file_done(
                        operation_id,
                        partition=partition.root_path,
                    )

            out.append(processed)

        if self._progress_tracker is not None and operation_id:
            self._progress_tracker.mark_partition_done(operation_id)
        return out

    def _process_file(self, repo_root: str, file_path: str, generation: int) -> ReindexProcessedFile:
        full_path = os.path.join(repo_root, file_path)
        try:
            source = Path(full_path).read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError) as exc:
            return ReindexProcessedFile(
                file_path=file_path,
                symbols=[],
                edges=[],
                chunks=[],
                failed=True,
                error=str(exc),
            )

        symbols, edges, _diags = self._parser.parse_file(file_path, source)
        symbols = [
            dataclasses.replace(s, index_generation=generation)
            for s in symbols
        ]
        edges = [
            dataclasses.replace(e, index_generation=generation)
            for e in edges
        ]

        chunks: list[Chunk] = []
        if self._chunker:
            chunks = self._chunker.chunk_file(file_path, source, symbols, generation)

        return ReindexProcessedFile(
            file_path=file_path,
            symbols=symbols,
            edges=edges,
            chunks=chunks,
        )

    def _get_changed_files(self, metadata: IndexMetadata) -> list[dict]:
        """Get files changed since the last indexed commit."""
        if not self._git:
            return []
        head_commit = metadata.workspace_state.head_commit
        if not head_commit:
            return []
        return self._git.get_changed_files_since(
            head_commit, include_worktree=True,
        )


@dataclass
class ReindexResult:
    files_changed: int = 0
    files_reindexed: int = 0
    files_deleted: int = 0
    files_failed: int = 0
    symbols_count: int = 0
    edges_count: int = 0
    generation: int = 0
    embedding_errors: int = 0
    needs_full_index: bool = False
    duration: float = 0.0
    operation_id: str | None = None
