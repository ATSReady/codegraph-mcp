"""Get inheritance/implementation hierarchy."""

from __future__ import annotations

from codegraph.domain.models import EdgeKind
from codegraph.domain.ports import SymbolStore


class GetHierarchyUseCase:
    """Retrieve inheritance hierarchy (ancestors or descendants) for a symbol."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def execute(
        self,
        symbol_id: str,
        direction: str = "ancestors",
    ) -> dict:
        if direction == "ancestors":
            edges, _ = self._store.get_edges(
                source_id=symbol_id, kind=EdgeKind.INHERITS,
            )
        else:  # descendants
            edges, _ = self._store.get_edges(
                target_id=symbol_id, kind=EdgeKind.INHERITS,
            )
        return {
            "hierarchy": [
                {
                    "source_symbol_id": e.source_symbol_id,
                    "target_symbol_id": e.target_symbol_id or "",
                    "kind": e.kind.value,
                }
                for e in edges
            ],
            "count": len(edges),
            "direction": direction,
        }
