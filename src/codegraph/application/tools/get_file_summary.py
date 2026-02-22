"""Get a structural summary of a file."""

from __future__ import annotations

from codegraph.domain.models import EdgeKind
from codegraph.domain.ports import SymbolStore


class GetFileSummaryUseCase:
    """Return a summary of symbols and edges in a given file."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

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
            "_naive_tokens": max(500, len(symbols) * 200),
        }
