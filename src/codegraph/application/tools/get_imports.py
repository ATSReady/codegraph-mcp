"""Get import edges for a file or symbol."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import EdgeKind
from codegraph.domain.ports import SymbolStore


class GetImportsUseCase:
    """Retrieve import edges, optionally filtered by file or source symbol."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

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
        }
