"""Semantic search over code chunks."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.ports import SymbolStore, EmbeddingProvider


class SemanticSearchUseCase:
    """Perform vector-similarity search over indexed code chunks."""

    def __init__(
        self,
        store: SymbolStore,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ) -> None:
        self._store = store
        self._embedder = embedding_provider

    def _get_naive_from_results(self, results: list) -> int:
        """Naive baseline = sum of token costs of unique files from search results."""
        meta = self._store.get_metadata()
        if not meta or not meta.repo_stats:
            return 0
        unique_files = {r.file_path for r in results}
        return sum(
            meta.repo_stats.per_file_tokens.get(fp, 0)
            for fp in unique_files
        )

    async def execute(
        self,
        query: str,
        max_results: int = 10,
        file_filter: Optional[str] = None,
    ) -> dict:
        if self._embedder is None:
            return {"error": "No embedding provider configured", "results": []}

        query_vector = await self._embedder.embed_single(query)
        results = self._store.vector_search(
            query_vector=query_vector,
            top_k=max_results,
            file_filter=file_filter,
        )
        return {
            "results": [
                {
                    "chunk_id": r.chunk_id,
                    "file_path": r.file_path,
                    "start_line": r.start_line,
                    "end_line": r.end_line,
                    "score": 0.0,
                    "symbol_ids": r.symbol_ids,
                    "content_preview": (
                        (r.content[:200] + "...")
                        if len(r.content) > 200
                        else r.content
                    ),
                }
                for r in results
            ],
            "count": len(results),
            "query": query,
            "_naive_tokens": self._get_naive_from_results(results),
        }
