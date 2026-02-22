"""Shared types and utilities for embedding providers."""
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


def normalize_l2(vec: list[float]) -> list[float]:
    """L2-normalize a vector. Returns zero vector if norm is zero."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def pack_batches(
    texts: list[str],
    max_batch_size: int = 64,
) -> list[list[int]]:
    """Split text indices into batches of at most *max_batch_size*.

    Returns a list of index-lists, e.g. [[0,1,2], [3,4,5]].
    """
    batches: list[list[int]] = []
    current: list[int] = []
    for i in range(len(texts)):
        current.append(i)
        if len(current) >= max_batch_size:
            batches.append(current)
            current = []
    if current:
        batches.append(current)
    return batches
