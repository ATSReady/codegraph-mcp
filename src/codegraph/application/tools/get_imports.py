"""Get import edges for a file or symbol."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import EdgeKind
from codegraph.domain.ports import SymbolStore


class GetImportsUseCase:
    """Retrieve import edges, optionally filtered by file or source symbol."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def _get_naive_tokens(self, file_path: str) -> int:
        """Get naive token baseline from actual file size in index."""
        meta = self._store.get_metadata()
        if meta and meta.repo_stats and file_path in meta.repo_stats.per_file_tokens:
            return meta.repo_stats.per_file_tokens[file_path]
        if meta and meta.repo_stats:
            return meta.repo_stats.median_file_tokens
        return 0

    def execute(
        self,
        file_path: Optional[str] = None,
        symbol_id: Optional[str] = None,
    ) -> dict:
        edges, _ = self._store.get_edges(
            source_id=symbol_id,
            file_path=file_path,
            kind=EdgeKind.IMPORTS,
        )

        if file_path:
            naive_tokens = self._get_naive_tokens(file_path)
        else:
            meta = self._store.get_metadata()
            naive_tokens = meta.repo_stats.median_file_tokens if meta and meta.repo_stats else 0

        return {
            "imports": [
                {
                    "edge_id": e.edge_id8,
                    "source_symbol_id": e.source_symbol_id,
                    "target_symbol_id": e.target_symbol_id or "",
                    "ref_text": e.ref_text,
                    "file_path": e.file_path,
                    "line": e.start_line,
                }
                for e in edges
            ],
            "count": len(edges),
            "_naive_tokens": naive_tokens,
        }
