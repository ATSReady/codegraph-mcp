"""Incremental reindex use case."""
from __future__ import annotations

import dataclasses
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from codegraph.domain.models import Symbol, Edge, Chunk
from codegraph.domain.workspace import IndexMetadata


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
    ) -> None:
        self._store = store
        self._parser = parser
        self._git = git_client
        self._embedder = embedding_provider
        self._chunker = chunker
        self._progress_tracker = progress_tracker

    def execute(self, repo_root: str) -> ReindexResult:
        """Run incremental reindex on changed files only."""
        start = time.time()
        result = ReindexResult()

        metadata = self._store.get_metadata()
        if metadata is None:
            result.needs_full_index = True
            return result

        generation = metadata.generation + 1

        # Get changed files since last indexed commit
        changed = self._get_changed_files(metadata)
        result.files_changed = len(changed)

        if not changed:
            result.duration = time.time() - start
            return result

        deleted_files = [
            f["file_path"] for f in changed if f.get("status") == "deleted"
        ]
        modified_files = [
            f["file_path"] for f in changed if f.get("status") != "deleted"
        ]

        # Process deletions
        for fp in deleted_files:
            self._store.delete_symbols_by_file(fp)
            self._store.delete_edges_by_file(fp)
            self._store.delete_chunks_by_file(fp)
            result.files_deleted += 1

        # Process modifications/additions
        all_symbols: list[Symbol] = []
        all_edges: list[Edge] = []
        all_chunks: list[Chunk] = []

        for file_path in modified_files:
            full_path = os.path.join(repo_root, file_path)
            try:
                source = Path(full_path).read_text(
                    encoding="utf-8", errors="replace",
                )
            except (OSError, UnicodeDecodeError):
                result.files_failed += 1
                continue

            # Delete old data for this file before re-parsing
            self._store.delete_symbols_by_file(file_path)
            self._store.delete_edges_by_file(file_path)
            self._store.delete_chunks_by_file(file_path)

            # Parse fresh
            symbols, edges, _diags = self._parser.parse_file(file_path, source)

            # Stamp generation (frozen dataclasses)
            symbols = [
                dataclasses.replace(s, index_generation=generation)
                for s in symbols
            ]
            edges = [
                dataclasses.replace(e, index_generation=generation)
                for e in edges
            ]

            all_symbols.extend(symbols)
            all_edges.extend(edges)

            if self._chunker:
                chunks = self._chunker.chunk_file(
                    file_path, source, symbols, generation,
                )
                all_chunks.extend(chunks)

            result.files_reindexed += 1

        # Write to store
        if all_symbols:
            self._store.upsert_symbols(all_symbols)
        if all_edges:
            self._store.upsert_edges(all_edges)
        if all_chunks:
            self._store.upsert_chunks(all_chunks)

        # Embed if provider available
        if self._embedder and all_chunks:
            try:
                texts = [c.embedding_text or c.content for c in all_chunks]
                vectors = self._embedder.embed_batch(texts)
                for i, chunk in enumerate(all_chunks):
                    if i < len(vectors):
                        chunk.vector = vectors[i]
                        chunk.has_vector = True
                # Re-upsert chunks with vectors
                self._store.upsert_chunks(all_chunks)
            except Exception:
                result.embedding_errors += 1

        # Update metadata
        head_commit = self._git.get_head_commit() if self._git else None
        metadata.generation = generation
        if head_commit:
            metadata.workspace_state.head_commit = head_commit
        self._store.set_metadata(metadata)

        result.symbols_count = len(all_symbols)
        result.edges_count = len(all_edges)
        result.generation = generation
        result.duration = time.time() - start
        return result

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
