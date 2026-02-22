"""Get call edges from/to a symbol."""

from __future__ import annotations

from codegraph.domain.models import EdgeKind
from codegraph.domain.ports import SymbolStore


class GetCallGraphUseCase:
    """Retrieve outgoing or incoming call edges for a symbol."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def execute(
        self,
        symbol_id: str,
        direction: str = "outgoing",
    ) -> dict:
        if direction == "outgoing":
            edges, _ = self._store.get_edges(
                source_id=symbol_id, kind=EdgeKind.CALLS,
            )
        else:
            edges, _ = self._store.get_edges(
                target_id=symbol_id, kind=EdgeKind.CALLS,
            )
        return {
            "calls": [
                {
                    "source_symbol_id": e.source_symbol_id,
                    "target_symbol_id": e.target_symbol_id or "",
                    "ref_text": e.ref_text,
                    "file_path": e.file_path,
                    "line": e.start_line,
                }
                for e in edges
            ],
            "count": len(edges),
            "direction": direction,
            "_naive_tokens": max(2000, len(edges) * 500),
        }
