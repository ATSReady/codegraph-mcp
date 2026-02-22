"""Tests for MetricsTracker application service."""
import json
import os

import pytest

from codegraph.application.metrics_tracker import MetricsTracker


class TestMetricsTrackerRecord:
    def test_record_and_get_metrics(self):
        tracker = MetricsTracker()
        tracker.record("get_snippet", naive_tokens=5000, actual_tokens=800)
        tracker.record("get_snippet", naive_tokens=3000, actual_tokens=600)
        tracker.record("get_symbols", naive_tokens=2000, actual_tokens=300)

        metrics = tracker.get_session_metrics()
        assert len(metrics.tools) == 2

        snippet = next(t for t in metrics.tools if t.tool == "get_snippet")
        assert snippet.calls == 2
        assert snippet.naive_tokens == 8000
        assert snippet.actual_tokens == 1400
        assert snippet.tokens_saved == 6600

        symbols = next(t for t in metrics.tools if t.tool == "get_symbols")
        assert symbols.calls == 1

        assert metrics.total_saved == 8300

    def test_session_tokens_saved(self):
        tracker = MetricsTracker()
        assert tracker.session_tokens_saved == 0
        tracker.record("get_snippet", naive_tokens=5000, actual_tokens=800)
        assert tracker.session_tokens_saved == 4200


class TestMetricsTrackerPersist:
    def test_persist_and_load(self, tmp_path):
        tracker = MetricsTracker(metrics_dir=str(tmp_path))
        tracker.record("get_snippet", naive_tokens=5000, actual_tokens=800)
        tracker.persist()

        last = tmp_path / "last-session.json"
        assert last.exists()
        data = json.loads(last.read_text())
        assert data["metrics"]["total_saved"] == 4200

        session_file = tmp_path / "sessions" / f"{tracker.session_id}.json"
        assert session_file.exists()

    def test_persist_noop_without_dir(self):
        tracker = MetricsTracker()  # no metrics_dir
        tracker.record("get_snippet", naive_tokens=5000, actual_tokens=800)
        tracker.persist()  # should not raise


class TestMetricsTrackerFormat:
    def test_format_markdown(self):
        tracker = MetricsTracker()
        tracker.record("get_snippet", naive_tokens=5000, actual_tokens=800)
        tracker.record("get_symbols", naive_tokens=2000, actual_tokens=300)
        md = tracker.format_markdown()
        assert "get_snippet" in md
        assert "get_symbols" in md
        assert "Tokens" in md or "tokens" in md
