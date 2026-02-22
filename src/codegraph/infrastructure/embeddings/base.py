"""Base classes and utilities for embedding providers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class EmbeddingResult:
    """Result from embedding a batch of texts."""
    vectors: list[list[float]]
    model: str
    dimension: int
    token_count: int = 0


def normalize_l2(vector: list[float]) -> list[float]:
    """L2-normalize a vector to unit length."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


def estimate_tokens(text: str, chars_per_token: float = 4.0) -> int:
    """Estimate token count from text using character heuristic."""
    return max(1, int(len(text) / chars_per_token))


def pack_batches(
    texts: list[str],
    max_batch_size: int = 64,
    max_batch_tokens: int = 8192,
    chars_per_token: float = 4.0,
) -> list[list[int]]:
    """Pack texts into batches respecting size and token limits.
    
    Returns list of batches, where each batch is a list of indices into the original texts.
    Sorts by descending estimated token count for efficient packing.
    """
    # Create (estimated_tokens, original_index) pairs, sort descending
    indexed = [(estimate_tokens(t, chars_per_token), i) for i, t in enumerate(texts)]
    indexed.sort(reverse=True)
    
    batches: list[list[int]] = []
    current_batch: list[int] = []
    current_tokens = 0
    
    for est_tokens, idx in indexed:
        if current_batch and (
            len(current_batch) >= max_batch_size
            or current_tokens + est_tokens > max_batch_tokens
        ):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append(idx)
        current_tokens += est_tokens
    
    if current_batch:
        batches.append(current_batch)
    
    return batches
