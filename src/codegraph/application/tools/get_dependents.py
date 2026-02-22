"""Find who depends on a symbol."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.ports import SymbolStore


class GetDependentsUseCase:
    """Find all edges targeting a given symbol (dependents)."""

    def __init__(self, store: SymbolStore) -> None:
        self._store = store

    def _get_naive_from_edges(self, edges: list) -> int:
        """Naive baseline = sum of token costs of unique files containing edges."""
        meta = self._store.get_metadata()
        if not meta or not meta.repo_stats:
            return 0
        unique_files = {e.file_path for e in edges}
        return sum(
            meta.repo_stats.per_file_tokens.get(fp, 0)
            for fp in unique_files
        )

    def execute(
        self,
        symbol_id: Optional[str] = None,
    ) -> dict:
        edges, _ = self._store.get_edges(target_id=symbol_id)
        return {
            "dependents": [
                {
                    "source_symbol_id": e.source_symbol_id,
                    "kind": e.kind.value,
                    "ref_text": e.ref_text,
                    "file_path": e.file_path,
                    "line": e.start_line,
                }
                for e in edges
            ],
            "count": len(edges),
            "_naive_tokens": self._get_naive_from_edges(edges),
        }
