"""Base types and utilities for embedding providers."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EmbeddingResult:
    """Result from an embedding operation."""

    vectors: list[list[float]]
    model: str
    dimension: int
    token_count: int = 0
    metadata: dict = field(default_factory=dict)


def normalize_l2(vec: list[float]) -> list[float]:
    """Normalize a vector to unit length (L2 norm)."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def pack_batches(
    texts: list[str],
    max_batch_size: int = 64,
) -> list[list[int]]:
    """Split text indices into batches of at most max_batch_size.

    Returns a list of index-lists. Each inner list contains the original
    indices of the texts that should be sent together.
    """
    batches: list[list[int]] = []
    for start in range(0, len(texts), max_batch_size):
        end = min(start + max_batch_size, len(texts))
        batches.append(list(range(start, end)))
    return batches
