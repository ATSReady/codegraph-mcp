"""Tests for repo overview including RepoStats."""
import math
from unittest.mock import MagicMock

from codegraph.domain.workspace import (
    FileManifestEntry,
    IndexMetadata,
    WorkspaceState,
    ParseStatus,
    RepoStats,
)
from codegraph.application.tools.get_repo_overview import GetRepoOverviewUseCase


class TestRepoOverviewStats:
    def test_includes_repo_stats(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 400, ParseStatus.OK),
            "b.py": FileManifestEntry("b.py", "python", 0.0, 600, ParseStatus.OK),
        }
        stats = RepoStats.from_manifest(manifest)
        metadata = IndexMetadata(
            workspace_state=WorkspaceState("abc", "abc", False),
            embedding=MagicMock(),
            generation=1,
            file_manifest=manifest,
            repo_stats=stats,
        )
        store = MagicMock()
        store.get_metadata.return_value = metadata
        result = GetRepoOverviewUseCase(store).execute()

        assert result["total_tokens"] == stats.total_tokens
        assert result["median_file_tokens"] == stats.median_file_tokens
        assert result["_naive_tokens"] == stats.total_tokens
