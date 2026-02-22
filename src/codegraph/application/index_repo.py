"""Full repository indexing use case."""
from __future__ import annotations

import dataclasses
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from codegraph.domain.models import Symbol, Edge, Chunk
from codegraph.domain.workspace import (
    IndexMetadata,
    WorkspaceState,
    EmbeddingMetadata,
    FileManifestEntry,
    FileDiagnostic,
    ParseStatus,
)
from codegraph.domain.config import CodegraphConfig


class IndexRepoUseCase:
    """Orchestrates full repository indexing."""

    def __init__(
        self,
        store,  # SymbolStore protocol
        parser,  # TreeSitterParser
        git_client,  # GitClient protocol
        embedding_provider=None,  # EmbeddingProvider protocol (optional)
        chunker=None,  # CodeChunker (optional)
        config: Optional[CodegraphConfig] = None,
        progress_tracker=None,
    ) -> None:
        self._store = store
        self._parser = parser
        self._git = git_client
        self._embedder = embedding_provider
        self._chunker = chunker
        self._config = config or CodegraphConfig()
        self._progress_tracker = progress_tracker

    def execute(self, repo_root: str, force: bool = False) -> IndexResult:
        """Run the full indexing pipeline."""
        start = time.time()
        result = IndexResult()

        # Step 1: Discover files
        files = self._discover_files(repo_root)
        result.files_discovered = len(files)

        # Step 2: Determine generation
        metadata = self._store.get_metadata()
        generation = (metadata.generation + 1) if metadata else 1

        # Step 3: Parse files
        all_symbols: list[Symbol] = []
        all_edges: list[Edge] = []
        all_chunks: list[Chunk] = []
        all_diagnostics: list[FileDiagnostic] = []
        manifest: dict[str, FileManifestEntry] = {}

        for file_path in files:
            full_path = os.path.join(repo_root, file_path)
            try:
                source = Path(full_path).read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                result.files_failed += 1
                continue

            symbols, edges, diags = self._parser.parse_file(file_path, source)

            # Stamp generation on symbols and edges (frozen dataclasses)
            symbols = [
                dataclasses.replace(s, index_generation=generation) for s in symbols
            ]
            edges = [
                dataclasses.replace(e, index_generation=generation) for e in edges
            ]

            all_symbols.extend(symbols)
            all_edges.extend(edges)
            all_diagnostics.extend(diags)

            # Chunking
            if self._chunker:
                chunks = self._chunker.chunk_file(
                    file_path, source, symbols, generation,
                )
                all_chunks.extend(chunks)

            # Build manifest entry
            parse_status = ParseStatus.OK
            if diags:
                _rank = {"ok": 0, "warn": 1, "error": 2}
                parse_status = max(
                    (d.parse_status for d in diags),
                    key=lambda s: _rank.get(s.value, 0),
                    default=ParseStatus.OK,
                )

            file_size = 0
            mtime = 0.0
            if os.path.exists(full_path):
                stat = os.stat(full_path)
                mtime = stat.st_mtime
                file_size = stat.st_size

            manifest[file_path] = FileManifestEntry(
                file_path=file_path,
                language=symbols[0].language if symbols else "unknown",
                mtime=mtime,
                size=file_size,
                parse_status=parse_status,
            )
            result.files_indexed += 1

        # Step 4: Embed chunks if provider available
        if self._embedder and all_chunks:
            try:
                texts = [c.embedding_text or c.content for c in all_chunks]
                vectors = self._embedder.embed_batch(texts)
                for i, chunk in enumerate(all_chunks):
                    if i < len(vectors):
                        chunk.vector = vectors[i]
                        chunk.has_vector = True
                result.chunks_embedded = len(all_chunks)
            except Exception:
                result.embedding_errors += 1

        # Step 5: Write to store
        if all_symbols:
            self._store.upsert_symbols(all_symbols)
        if all_edges:
            self._store.upsert_edges(all_edges)
        if all_chunks:
            self._store.upsert_chunks(all_chunks)
        if all_diagnostics:
            self._store.set_diagnostics(all_diagnostics)

        result.symbols_count = len(all_symbols)
        result.edges_count = len(all_edges)
        result.chunks_count = len(all_chunks)

        # Step 6: Update metadata
        head_commit = self._git.get_head_commit() if self._git else None

        embedding_meta = EmbeddingMetadata(
            provider_id=self._embedder.name if self._embedder else "none",
            model="none",
            model_revision=None,
            runtime="none",
            device="none",
            actual_dimension=self._embedder.dimension if self._embedder else 0,
            requested_dimension=None,
            config_hash="",
            input_version=1,
            normalize="none",
        )

        workspace_state = WorkspaceState(
            head_commit=head_commit or "",
            index_base=head_commit or "",
            worktree_dirty=False,
        )

        from codegraph.domain.workspace import RepoStats

        repo_stats = RepoStats.from_manifest(manifest)

        new_metadata = IndexMetadata(
            workspace_state=workspace_state,
            embedding=embedding_meta,
            generation=generation,
            file_manifest=manifest,
            repo_stats=repo_stats,
        )
        self._store.set_metadata(new_metadata)

        result.duration = time.time() - start
        result.generation = generation
        return result

    def _discover_files(self, repo_root: str) -> list[str]:
        """Get list of tracked files, filtered by language support."""
        from codegraph.infrastructure.parsers.languages import detect_language

        if self._git and self._git.is_git_repo():
            all_files = self._git.list_tracked_files()
        else:
            all_files = self._walk_directory(repo_root)

        # Filter to supported languages and exclude patterns
        exclude_patterns = self._config.index.exclude if self._config else []
        supported = []
        for f in all_files:
            if detect_language(f) is not None:
                if not self._is_excluded(f, exclude_patterns):
                    supported.append(f)
        return supported

    def _walk_directory(self, repo_root: str) -> list[str]:
        """Walk directory for files."""
        files = []
        for root, dirs, filenames in os.walk(repo_root):
            # Skip hidden and common non-source directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in (
                    "node_modules", "__pycache__", ".git",
                    "venv", ".venv", "dist", "build",
                )
            ]
            for filename in filenames:
                full = os.path.join(root, filename)
                rel = os.path.relpath(full, repo_root)
                files.append(rel)
        return files

    def _is_excluded(self, path: str, patterns: list[str]) -> bool:
        """Check if file matches exclude patterns (simple glob)."""
        import fnmatch

        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False


@dataclass
class IndexResult:
    files_discovered: int = 0
    files_indexed: int = 0
    files_failed: int = 0
    symbols_count: int = 0
    edges_count: int = 0
    chunks_count: int = 0
    chunks_embedded: int = 0
    embedding_errors: int = 0
    generation: int = 0
    duration: float = 0.0
