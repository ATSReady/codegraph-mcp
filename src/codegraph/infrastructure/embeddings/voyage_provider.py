"""Voyage AI embedding API provider."""
from __future__ import annotations

import json
import os
import time
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from codegraph.infrastructure.embeddings.base import (
    EmbeddingResult,
    normalize_l2,
    pack_batches,
)


class VoyageProvider:
    """Embedding provider using Voyage AI's API.
    
    Implements the EmbeddingProvider protocol from domain.ports.
    """

    provider_name = "voyage"
    max_tokens = 16000
    API_URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(
        self,
        model: str = "voyage-code-2",
        api_key: Optional[str] = None,
        dimension: Optional[int] = None,
        normalize: bool = True,
        batch_size: int = 64,
        max_concurrent: int = 4,
        max_retries: int = 3,
    ) -> None:
        self.model_name = model
        self._api_key = api_key or os.environ.get("VOYAGE_API_KEY", "")
        self.dimension = dimension or self._default_dimension(model)
        self._normalize = normalize
        self._batch_size = batch_size
        self._max_concurrent = max_concurrent
        self._max_retries = max_retries

    def _default_dimension(self, model: str) -> int:
        defaults = {
            "voyage-code-2": 1536,
            "voyage-code-3": 1024,
            "voyage-2": 1024,
            "voyage-large-2": 1536,
        }
        return defaults.get(model, 1024)

    def _call_api(self, texts: list[str]) -> dict:
        payload = {
            "input": texts,
            "model": self.model_name,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        data = json.dumps(payload).encode("utf-8")
        req = Request(self.API_URL, data=data, headers=headers, method="POST")

        for attempt in range(self._max_retries):
            try:
                with urlopen(req) as resp:
                    return json.loads(resp.read().decode())
            except HTTPError as e:
                if e.code == 429:
                    wait = min(2 ** attempt, 30)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"Voyage API failed after {self._max_retries} retries")

    def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self.model_name, dimension=self.dimension)

        if not self._api_key:
            raise RuntimeError("Voyage API key not set. Set VOYAGE_API_KEY environment variable.")

        all_vectors: list[list[float]] = [[] for _ in texts]
        total_tokens = 0

        batches = pack_batches(texts, max_batch_size=self._batch_size)

        for batch_indices in batches:
            batch_texts = [texts[i] for i in batch_indices]
            response = self._call_api(batch_texts)

            usage = response.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)

            for i, item in enumerate(response["data"]):
                vec = item["embedding"]
                if self._normalize:
                    vec = normalize_l2(vec)
                all_vectors[batch_indices[i]] = vec

        return EmbeddingResult(
            vectors=all_vectors,
            model=self.model_name,
            dimension=self.dimension,
            token_count=total_tokens,
        )

    def embed_single(self, text: str) -> list[float]:
        result = self.embed([text])
        return result.vectors[0]
