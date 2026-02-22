"""Get a structural summary of a file."""

from __future__ import annotations

from codegraph.domain.models import EdgeKind
from codegraph.domain.ports import SymbolStore


class GetFileSummaryUseCase:
    """Return a summary of symbols and edges in a given file."""

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

    def execute(self, file_path: str) -> dict:
        symbols, _ = self._store.query_symbols(
            file_path=file_path, max_results=500,
        )
        edges, _ = self._store.get_edges(file_path=file_path)

        return {
            "file_path": file_path,
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind.value,
                    "start_line": s.start_line,
                    "end_line": s.end_line,
                    "signature": s.signature,
                }
                for s in symbols
            ],
            "symbol_count": len(symbols),
            "edge_count": len(edges),
            "import_count": len(
                [e for e in edges if e.kind == EdgeKind.IMPORTS]
            ),
            "_naive_tokens": self._get_naive_tokens(file_path),
        }
