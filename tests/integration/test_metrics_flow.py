"""Integration test: tool calls accumulate metrics and persist."""
import json
import os

import pytest

from codegraph.application.metrics_tracker import MetricsTracker
from codegraph.application.tools.get_snippet import GetSnippetUseCase
from codegraph.domain.metrics import estimate_tokens


class TestMetricsEndToEnd:
    def test_snippet_metrics_flow(self, tmp_path):
        """get_snippet -> MetricsTracker -> persist -> read back."""
        # Setup: create a source file
        src = tmp_path / "src"
        src.mkdir()
        big_file = src / "big.py"
        content = "\n".join(f"def func_{i}(): return {i}" for i in range(200))
        big_file.write_text(content)

        # Run use case
        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("src/big.py", start_line=50, end_line=55)

        # Extract naive estimate
        naive = result.pop("_naive_tokens")
        actual = estimate_tokens(json.dumps(result))

        # Track
        metrics_dir = str(tmp_path / ".codegraph" / "metrics")
        tracker = MetricsTracker(metrics_dir=metrics_dir)
        tracker.record("get_snippet", naive_tokens=naive, actual_tokens=actual)
        tracker.persist()

        # Verify persisted
        last = json.loads(
            open(os.path.join(metrics_dir, "last-session.json")).read()
        )
        assert last["metrics"]["total_saved"] > 0
        assert last["metrics"]["tools"][0]["tool"] == "get_snippet"

        # Verify savings are substantial (snippet of 6 lines vs 200-line file)
        assert last["metrics"]["total_saved"] > 1000

    def test_multiple_tools_accumulate(self, tmp_path):
        """Multiple tool calls accumulate correctly."""
        metrics_dir = str(tmp_path / ".codegraph" / "metrics")
        tracker = MetricsTracker(metrics_dir=metrics_dir)

        # Simulate several tool calls
        tracker.record("get_snippet", naive_tokens=5000, actual_tokens=800)
        tracker.record("get_symbols", naive_tokens=3000, actual_tokens=400)
        tracker.record("get_snippet", naive_tokens=4000, actual_tokens=600)

        metrics = tracker.get_session_metrics()
        assert metrics.total_saved == 10200
        assert len(metrics.tools) == 2  # get_snippet and get_symbols

        # Persist and verify
        tracker.persist()
        last = json.loads(
            open(os.path.join(metrics_dir, "last-session.json")).read()
        )
        assert last["metrics"]["total_saved"] == 10200
        assert last["metrics"]["percent_saved"] == pytest.approx(85.0, abs=0.1)
