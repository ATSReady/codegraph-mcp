"""Query symbols with filtering."""

from __future__ import annotations

import re
from typing import Optional

from codegraph.domain.models import Symbol, SymbolKind
from codegraph.domain.ports import SymbolStore


class GetSymbolsUseCase:
    """Retrieve symbols from the store with optional filtering."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def execute(
        self,
        file_path: Optional[str] = None,
        kind: Optional[SymbolKind] = None,
        name_pattern: Optional[str] = None,
        max_results: int = 50,
        cursor: Optional[str] = None,
    ) -> dict:
        symbols, next_cursor = self._store.query_symbols(
            file_path=file_path,
            kind=kind,
            max_results=max_results,
            cursor=cursor,
        )
        if name_pattern:
            pattern = re.compile(name_pattern, re.IGNORECASE)
            symbols = [s for s in symbols if pattern.search(s.name)]

        if file_path:
            naive_tokens = max(500, len(symbols) * 200)
        else:
            naive_tokens = max(1000, len(symbols) * 200)

        return {
            "symbols": [self._serialize(s) for s in symbols],
            "next_cursor": next_cursor,
            "count": len(symbols),
            "_naive_tokens": naive_tokens,
        }

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
        }
