"""Integration test: tool calls accumulate metrics and persist."""
import json
import math
import os
from unittest.mock import MagicMock

import pytest

from codegraph.application.metrics_tracker import MetricsTracker
from codegraph.application.tools.get_file_summary import GetFileSummaryUseCase
from codegraph.application.tools.get_repo_overview import GetRepoOverviewUseCase
from codegraph.application.tools.get_snippet import GetSnippetUseCase
from codegraph.application.tools.get_symbols import GetSymbolsUseCase
from codegraph.domain.metrics import TOKEN_FACTOR, estimate_tokens
from codegraph.domain.workspace import (
    EmbeddingMetadata,
    FileManifestEntry,
    IndexMetadata,
    ParseStatus,
    RepoStats,
    WorkspaceState,
)


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


class TestAccurateTokenSavings:
    """Integration tests verifying token savings are data-driven."""

    @pytest.fixture
    def indexed_store(self):
        """Create a mock store with realistic file manifest and RepoStats."""
        manifest = {
            "src/main.py": FileManifestEntry("src/main.py", "python", 0.0, 2500, ParseStatus.OK),
            "src/utils.py": FileManifestEntry("src/utils.py", "python", 0.0, 800, ParseStatus.OK),
            "src/models.py": FileManifestEntry("src/models.py", "python", 0.0, 4200, ParseStatus.OK),
            "src/api.py": FileManifestEntry("src/api.py", "python", 0.0, 1500, ParseStatus.OK),
            "tests/test_main.py": FileManifestEntry("tests/test_main.py", "python", 0.0, 1200, ParseStatus.OK),
        }
        stats = RepoStats.from_manifest(manifest)
        metadata = IndexMetadata(
            workspace_state=WorkspaceState("abc123", "abc123", False),
            embedding=MagicMock(),
            generation=1,
            file_manifest=manifest,
            repo_stats=stats,
        )
        store = MagicMock()
        store.get_metadata.return_value = metadata
        store.query_symbols.return_value = ([], None)
        store.get_edges.return_value = ([], None)
        return store, manifest, stats

    def test_file_summary_uses_actual_size(self, indexed_store):
        """get_file_summary should use the file's actual size, not a hardcoded formula."""
        store, manifest, stats = indexed_store
        result = GetFileSummaryUseCase(store).execute(file_path="src/main.py")

        naive = result["_naive_tokens"]
        expected = math.ceil(2500 * TOKEN_FACTOR)
        assert naive == expected, f"Expected {expected} from actual file size, got {naive}"

    def test_file_summary_not_hardcoded(self, indexed_store):
        """Different files should produce different naive token values."""
        store, manifest, stats = indexed_store

        result_small = GetFileSummaryUseCase(store).execute(file_path="src/utils.py")
        result_large = GetFileSummaryUseCase(store).execute(file_path="src/models.py")

        assert result_small["_naive_tokens"] != result_large["_naive_tokens"]
        assert result_small["_naive_tokens"] < result_large["_naive_tokens"]

    def test_repo_overview_reports_stats(self, indexed_store):
        """Repo overview should include total_tokens from RepoStats."""
        store, manifest, stats = indexed_store
        result = GetRepoOverviewUseCase(store).execute()

        assert result["total_tokens"] == stats.total_tokens
        assert result["median_file_tokens"] == stats.median_file_tokens
        assert result["_naive_tokens"] == stats.total_tokens

    def test_repo_stats_computed_correctly(self, indexed_store):
        """RepoStats should be populated with correct aggregate values."""
        store, manifest, stats = indexed_store

        assert stats.total_files == 5
        total_bytes = 2500 + 800 + 4200 + 1500 + 1200
        assert stats.total_bytes == total_bytes
        assert stats.total_tokens == math.ceil(total_bytes * TOKEN_FACTOR)
        assert len(stats.per_file_tokens) == 5

    def test_savings_flow_end_to_end(self, indexed_store):
        """Full flow: tool call -> extract naive -> compute actual -> verify savings are positive."""
        store, manifest, stats = indexed_store

        result = GetFileSummaryUseCase(store).execute(file_path="src/models.py")
        naive = result.pop("_naive_tokens")
        actual = estimate_tokens(json.dumps(result))

        # Naive should be based on actual 4200-byte file
        assert naive == math.ceil(4200 * TOKEN_FACTOR)
        # The summary (just symbol names) should be much smaller than reading the whole file
        assert actual < naive
        savings = naive - actual
        assert savings > 0
