"""Find all references to a symbol."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.ports import SymbolStore


class FindReferencesUseCase:
    """Find all edges that reference a given symbol."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def execute(
        self,
        symbol_id: Optional[str] = None,
    ) -> dict:
        edges, _ = self._store.get_edges(target_id=symbol_id)
        return {
            "references": [
                {
                    "source_symbol_id": e.source_symbol_id,
                    "kind": e.kind.value,
                    "ref_text": e.ref_text,
                    "file_path": e.file_path,
                    "start_line": e.start_line,
                    "column": e.column,
                }
                for e in edges
            ],
            "count": len(edges),
            "_naive_tokens": max(2000, len(edges) * 500),
        }
