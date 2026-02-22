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
            "_naive_tokens": max(3000, len(results) * 800),
        }
