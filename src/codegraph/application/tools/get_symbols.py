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

        meta = self._store.get_metadata()
        if file_path:
            naive_tokens = self._get_naive_tokens(file_path)
        else:
            naive_tokens = meta.repo_stats.total_tokens if meta and meta.repo_stats else 0

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
