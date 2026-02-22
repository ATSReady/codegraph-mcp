"""Local ONNX embedding provider using nomic-embed-text-v1.5."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal

from codegraph.infrastructure.embeddings.base import (
    EmbeddingResult,
    normalize_l2,
    pack_batches,
)


class LocalOnnxProvider:
    """Embedding provider using local ONNX Runtime inference.

    Implements the EmbeddingProvider protocol from domain.ports.
    """

    def __init__(
        self,
        model_name: str = "nomic-embed-text-v1.5",
        model_path: Optional[str] = None,
        dimension: Optional[int] = None,
        do_normalize: bool = True,
        batch_size: int = 64,
    ) -> None:
        self.model_name = model_name
        self._model_path = model_path
        self._do_normalize = do_normalize
        self._batch_size = batch_size
        self._session = None
        self._tokenizer = None

        # Protocol attributes
        self.name: str = "local"
        self.dimension: int = dimension or 768  # nomic default
        self.max_tokens: int = 8192
        self.normalize: Literal["none", "l2"] = "l2" if do_normalize else "none"
        self.supports_dimension_override: bool = False
        self.supports_batch: bool = True
        self.max_batch_tokens: Optional[int] = None

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Lazy load model and tokenizer."""
        if self._session is not None:
            return

        try:
            import onnxruntime as ort
        except ImportError:
            raise RuntimeError(
                "onnxruntime is required for local embedding provider. "
                "Install with: pip install onnxruntime"
            )

        model_path = self._resolve_model_path()
        if model_path is None:
            raise RuntimeError(
                f"Model {self.model_name} not found. "
                f"Download it or set model_path explicitly."
            )

        self._session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )
        self._load_tokenizer()

    def _resolve_model_path(self) -> Optional[Path]:
        """Find the ONNX model file."""
        if self._model_path:
            p = Path(self._model_path)
            if p.exists():
                return p
            return None

        # Check common locations
        cache_dir = Path.home() / ".cache" / "codegraph" / "models"
        for candidate in [
            cache_dir / self.model_name / "model.onnx",
            cache_dir / f"{self.model_name}.onnx",
        ]:
            if candidate.exists():
                return candidate

        # Try huggingface cache
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_cache.exists():
            for model_dir in hf_cache.iterdir():
                if self.model_name.replace("-", "") in model_dir.name.replace("-", ""):
                    onnx_file = model_dir / "model.onnx"
                    if onnx_file.exists():
                        return onnx_file

        return None

    def _load_tokenizer(self) -> None:
        """Load tokenizer, falling back to simple char-based approach."""
        try:
            from tokenizers import Tokenizer

            tokenizer_path = None
            if self._model_path:
                parent = Path(self._model_path).parent
                for name in ["tokenizer.json", "tokenizer.model"]:
                    if (parent / name).exists():
                        tokenizer_path = str(parent / name)
                        break
            if tokenizer_path:
                self._tokenizer = Tokenizer.from_file(tokenizer_path)
        except (ImportError, Exception):
            # Fall back to simple tokenization
            self._tokenizer = None

    # ------------------------------------------------------------------
    # Tokenization
    # ------------------------------------------------------------------

    def _tokenize(self, texts: list[str]) -> dict:
        """Tokenize texts for the model."""
        import numpy as np

        if self._tokenizer is not None:
            encoded = self._tokenizer.encode_batch(texts)
            max_len = min(max(len(e.ids) for e in encoded), self.max_tokens)
            input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
            attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
            for i, e in enumerate(encoded):
                length = min(len(e.ids), max_len)
                input_ids[i, :length] = e.ids[:length]
                attention_mask[i, :length] = 1
            return {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
        else:
            # Simple fallback: character codes (NOT production quality)
            max_len = 512
            input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
            attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
            for i, text in enumerate(texts):
                chars = [ord(c) % 30000 for c in text[:max_len]]
                input_ids[i, : len(chars)] = chars
                attention_mask[i, : len(chars)] = 1
            return {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }

    # ------------------------------------------------------------------
    # Token estimation
    # ------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> Optional[int]:
        """Rough token count estimate (~4 chars per token)."""
        return max(1, len(text) // 4)

    # ------------------------------------------------------------------
    # Embedding (core)
    # ------------------------------------------------------------------

    def _embed_sync(self, texts: list[str]) -> EmbeddingResult:
        """Synchronous embedding implementation."""
        self._ensure_loaded()

        if not texts:
            return EmbeddingResult(
                vectors=[], model=self.model_name, dimension=self.dimension
            )

        import numpy as np

        all_vectors: list[list[float]] = [[] for _ in texts]
        total_tokens = 0

        batches = pack_batches(texts, max_batch_size=self._batch_size)

        for batch_indices in batches:
            batch_texts = [texts[i] for i in batch_indices]
            inputs = self._tokenize(batch_texts)

            outputs = self._session.run(None, inputs)
            # Typically outputs[0] is the embedding matrix
            embeddings = outputs[0]

            # Mean pooling over sequence dimension
            if len(embeddings.shape) == 3:
                # (batch, seq_len, dim) -> mean pool -> (batch, dim)
                mask = inputs["attention_mask"]
                masked = embeddings * mask[:, :, np.newaxis]
                summed = masked.sum(axis=1)
                counts = mask.sum(axis=1, keepdims=True).clip(min=1)
                embeddings = summed / counts

            for j, idx in enumerate(batch_indices):
                vec = embeddings[j].tolist()
                if self.dimension and len(vec) > self.dimension:
                    vec = vec[: self.dimension]
                if self._do_normalize:
                    vec = normalize_l2(vec)
                all_vectors[idx] = vec

            total_tokens += int(inputs["attention_mask"].sum())

        return EmbeddingResult(
            vectors=all_vectors,
            model=self.model_name,
            dimension=self.dimension,
            token_count=total_tokens,
        )

    # ------------------------------------------------------------------
    # Protocol methods (async)
    # ------------------------------------------------------------------

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts (async protocol method)."""
        result = self._embed_sync(texts)
        return result.vectors

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text (async protocol method)."""
        result = self._embed_sync([text])
        return result.vectors[0]
