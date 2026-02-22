"""Tests for metrics domain types."""
import pytest

from codegraph.domain.metrics import ToolMetricEntry, SessionMetrics, estimate_tokens


class TestToolMetricEntry:
    def test_tokens_saved(self):
        entry = ToolMetricEntry(
            tool="get_snippet",
            calls=3,
            naive_tokens=9000,
            actual_tokens=1500,
        )
        assert entry.tokens_saved == 7500

    def test_no_negative_savings(self):
        entry = ToolMetricEntry(
            tool="get_diff",
            calls=1,
            naive_tokens=100,
            actual_tokens=200,
        )
        assert entry.tokens_saved == 0


class TestSessionMetrics:
    def test_aggregation(self):
        entries = [
            ToolMetricEntry(tool="get_snippet", calls=5, naive_tokens=10000, actual_tokens=2000),
            ToolMetricEntry(tool="get_symbols", calls=3, naive_tokens=5000, actual_tokens=500),
        ]
        metrics = SessionMetrics.from_entries(entries)
        assert metrics.total_naive == 15000
        assert metrics.total_actual == 2500
        assert metrics.total_saved == 12500
        assert metrics.percent_saved == pytest.approx(83.3, abs=0.1)

    def test_empty(self):
        metrics = SessionMetrics.from_entries([])
        assert metrics.total_saved == 0
        assert metrics.percent_saved == 0.0


class TestEstimateTokens:
    def test_basic(self):
        assert estimate_tokens("hello world") == 9  # ceil(11 * 0.75) = 9

    def test_empty_string(self):
        assert estimate_tokens("") == 0
