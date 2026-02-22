"""Domain types for token savings tracking."""
from __future__ import annotations

import math
from dataclasses import dataclass

TOKEN_FACTOR = 0.75


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length (chars * 0.75)."""
    if not text:
        return 0
    return math.ceil(len(text) * TOKEN_FACTOR)


@dataclass(frozen=True)
class ToolMetricEntry:
    """Accumulated metrics for a single tool within a session."""

    tool: str
    calls: int
    naive_tokens: int
    actual_tokens: int

    @property
    def tokens_saved(self) -> int:
        return max(0, self.naive_tokens - self.actual_tokens)


@dataclass(frozen=True)
class SessionMetrics:
    """Aggregated session-level metrics."""

    tools: list[ToolMetricEntry]
    total_naive: int
    total_actual: int
    total_saved: int
    percent_saved: float

    @classmethod
    def from_entries(cls, entries: list[ToolMetricEntry]) -> SessionMetrics:
        total_naive = sum(e.naive_tokens for e in entries)
        total_actual = sum(e.actual_tokens for e in entries)
        total_saved = max(0, total_naive - total_actual)
        pct = (total_saved / total_naive * 100) if total_naive > 0 else 0.0
        return cls(
            tools=entries,
            total_naive=total_naive,
            total_actual=total_actual,
            total_saved=total_saved,
            percent_saved=pct,
        )
