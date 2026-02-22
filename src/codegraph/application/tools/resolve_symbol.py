"""Resolve a symbol name to candidates."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import SymbolKind
from codegraph.domain.ports import SymbolStore


class ResolveSymbolUseCase:
    """Resolve a symbol name to matching candidates, with optional context."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def execute(
        self,
        name: str,
        kind: Optional[SymbolKind] = None,
        file_context: Optional[str] = None,
    ) -> dict:
        symbols, _ = self._store.query_symbols(kind=kind, max_results=200)
        matches = [s for s in symbols if s.name == name]

        if file_context:
            same_file = [s for s in matches if s.file_path == file_context]
            other_file = [s for s in matches if s.file_path != file_context]
            matches = same_file + other_file

        return {
            "candidates": [
                {
                    "symbol_id": s.symbol_id,
                    "symbol_key": s.symbol_key,
                    "name": s.name,
                    "kind": s.kind.value,
                    "file_path": s.file_path,
                    "signature": s.signature,
                }
                for s in matches
            ],
            "count": len(matches),
        }
