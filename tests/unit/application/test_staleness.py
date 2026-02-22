"""Tests for staleness checker and reindex guard."""
import pytest
from unittest.mock import MagicMock

from codegraph.application.staleness import (
    StalenessChecker,
    ReindexGuard,
    StalenessResult,
)
from codegraph.domain.workspace import (
    IndexMetadata,
    WorkspaceState,
    EmbeddingMetadata,
)


def _make_metadata(generation: int = 1, head_commit: str = "abc123") -> IndexMetadata:
    """Build a minimal valid IndexMetadata for testing."""
    return IndexMetadata(
        workspace_state=WorkspaceState(
            head_commit=head_commit,
            index_base=head_commit,
            worktree_dirty=False,
        ),
        embedding=EmbeddingMetadata(
            provider_id="none",
            model="none",
            model_revision=None,
            runtime="none",
            device="none",
            actual_dimension=0,
            requested_dimension=None,
            config_hash="",
            input_version=1,
            normalize="none",
        ),
        generation=generation,
    )


class TestStalenessChecker:
    def test_no_index_is_stale(self):
        store = MagicMock()
        store.get_metadata.return_value = None
        checker = StalenessChecker(store, MagicMock())
        result = checker.check()
        assert result.is_stale
        assert result.reason == "no_index"

    def test_head_changed_is_stale(self):
        store = MagicMock()
        store.get_metadata.return_value = _make_metadata(
            generation=1, head_commit="old_commit",
        )
        git = MagicMock()
        git.get_head_commit.return_value = "new_commit"
        git.get_changed_files_since.return_value = [
            {"file_path": "a.py", "status": "modified"},
        ]

        checker = StalenessChecker(store, git)
        result = checker.check()
        assert result.is_stale
        assert result.head_changed
        assert result.changed_file_count == 1

    def test_not_stale_when_matching(self):
        store = MagicMock()
        store.get_metadata.return_value = _make_metadata(
            generation=1, head_commit="abc123",
        )
        git = MagicMock()
        git.get_head_commit.return_value = "abc123"
        git.is_dirty.return_value = False

        checker = StalenessChecker(store, git)
        result = checker.check()
        assert not result.is_stale

    def test_dirty_worktree_is_stale(self):
        store = MagicMock()
        store.get_metadata.return_value = _make_metadata(
            generation=1, head_commit="abc123",
        )
        git = MagicMock()
        git.get_head_commit.return_value = "abc123"
        git.is_dirty.return_value = True

        checker = StalenessChecker(store, git)
        result = checker.check()
        assert result.is_stale
        assert result.reason == "worktree_dirty"

    def test_handles_exception_in_changed_files(self):
        store = MagicMock()
        store.get_metadata.return_value = _make_metadata(
            generation=1, head_commit="old_commit",
        )
        git = MagicMock()
        git.get_head_commit.return_value = "new_commit"
        git.get_changed_files_since.side_effect = RuntimeError("git error")

        checker = StalenessChecker(store, git)
        result = checker.check()
        assert result.is_stale
        assert result.changed_file_count == -1


class TestReindexGuard:
    def test_try_start_succeeds(self):
        guard = ReindexGuard()
        assert guard.try_start() is True
        assert guard.is_running

    def test_try_start_fails_when_running(self):
        guard = ReindexGuard()
        guard.try_start()
        assert guard.try_start() is False
        assert guard.is_pending

    def test_finish_returns_pending(self):
        guard = ReindexGuard()
        guard.try_start()
        guard.try_start()  # Sets pending
        pending = guard.finish()
        assert pending is True
        assert not guard.is_running

    def test_finish_clears_pending(self):
        guard = ReindexGuard()
        guard.try_start()
        pending = guard.finish()
        assert pending is False

    def test_should_block_few_files(self):
        guard = ReindexGuard()
        staleness = StalenessResult(is_stale=True, changed_file_count=3)
        assert guard.should_block(staleness, max_files=5) is True

    def test_should_not_block_many_files(self):
        guard = ReindexGuard()
        staleness = StalenessResult(is_stale=True, changed_file_count=20)
        assert guard.should_block(staleness, max_files=5) is False

    def test_should_not_block_when_not_stale(self):
        guard = ReindexGuard()
        staleness = StalenessResult(is_stale=False)
        assert guard.should_block(staleness) is False

    def test_can_restart_after_finish(self):
        guard = ReindexGuard()
        guard.try_start()
        guard.finish()
        assert guard.try_start() is True
        assert guard.is_running
