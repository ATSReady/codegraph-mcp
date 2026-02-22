"""OpenAI embedding API provider."""
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


class OpenAIProvider:
    """Embedding provider using OpenAI's API.
    
    Implements the EmbeddingProvider protocol from domain.ports.
    Uses urllib to avoid requiring the openai package.
    """

    provider_name = "openai"
    max_tokens = 8191
    API_URL = "https://api.openai.com/v1/embeddings"

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        dimension: Optional[int] = None,
        normalize: bool = True,
        batch_size: int = 64,
        max_concurrent: int = 4,
        max_retries: int = 3,
    ) -> None:
        self.model_name = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.dimension = dimension or self._default_dimension(model)
        self._normalize = normalize
        self._batch_size = batch_size
        self._max_concurrent = max_concurrent
        self._max_retries = max_retries

    def _default_dimension(self, model: str) -> int:
        defaults = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return defaults.get(model, 1536)

    def _call_api(self, texts: list[str]) -> dict:
        """Make a single API call."""
        payload = {
            "input": texts,
            "model": self.model_name,
        }
        if self.dimension:
            payload["dimensions"] = self.dimension

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
                if e.code == 429:  # Rate limit
                    wait = min(2 ** attempt, 30)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"OpenAI API failed after {self._max_retries} retries")

    def embed(self, texts: list[str]) -> EmbeddingResult:
        """Embed a list of texts using OpenAI API."""
        if not texts:
            return EmbeddingResult(vectors=[], model=self.model_name, dimension=self.dimension)

        if not self._api_key:
            raise RuntimeError("OpenAI API key not set. Set OPENAI_API_KEY environment variable.")

        all_vectors: list[list[float]] = [[] for _ in texts]
        total_tokens = 0

        batches = pack_batches(texts, max_batch_size=self._batch_size)

        for batch_indices in batches:
            batch_texts = [texts[i] for i in batch_indices]
            response = self._call_api(batch_texts)

            usage = response.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)

            for item in response["data"]:
                vec = item["embedding"]
                if self._normalize:
                    vec = normalize_l2(vec)
                orig_idx = batch_indices[item["index"]]
                all_vectors[orig_idx] = vec

        return EmbeddingResult(
            vectors=all_vectors,
            model=self.model_name,
            dimension=self.dimension,
            token_count=total_tokens,
        )

    def embed_single(self, text: str) -> list[float]:
        result = self.embed([text])
        return result.vectors[0]
