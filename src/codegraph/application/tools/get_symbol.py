"""Get a single symbol by ID or key."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import Symbol
from codegraph.domain.ports import SymbolStore


class GetSymbolUseCase:
    """Retrieve a single symbol by its symbol_id or symbol_key."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def execute(
        self,
        symbol_id: Optional[str] = None,
        symbol_key: Optional[str] = None,
    ) -> dict:
        if symbol_id:
            symbol = self._store.get_symbol(symbol_id)
        elif symbol_key:
            symbol = self._store.get_symbol_by_key(symbol_key)
        else:
            return {"error": "Provide symbol_id or symbol_key"}

        if symbol is None:
            return {"symbol": None, "_naive_tokens": 3000}
        return {"symbol": self._serialize(symbol), "_naive_tokens": 3000}

    @staticmethod
    def _serialize(s: Symbol) -> dict:
        return {
            "symbol_id": s.symbol_id,
            "name": s.name,
            "kind": s.kind.value,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "signature": s.signature,
            "symbol_key": s.symbol_key,
            "container_name": s.container_name,
            "module_path": s.module_path,
            "docstring": s.docstring,
        }
