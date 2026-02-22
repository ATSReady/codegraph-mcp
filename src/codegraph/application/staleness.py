"""Staleness checking and reindex guard."""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class StalenessResult:
    is_stale: bool = False
    reason: str = ""
    changed_file_count: int = 0
    head_changed: bool = False


class StalenessChecker:
    """Checks if the index is stale relative to the repository state."""

    def __init__(self, store, git_client) -> None:
        self._store = store
        self._git = git_client

    def check(self) -> StalenessResult:
        """Compare stored metadata against current repo state."""
        result = StalenessResult()
        metadata = self._store.get_metadata()

        if metadata is None:
            result.is_stale = True
            result.reason = "no_index"
            return result

        # Check HEAD commit
        current_head = self._git.get_head_commit() if self._git else None
        stored_head = metadata.workspace_state.head_commit
        if current_head and stored_head and current_head != stored_head:
            result.is_stale = True
            result.head_changed = True
            result.reason = "head_changed"
            # Count changed files
            try:
                changed = self._git.get_changed_files_since(
                    stored_head, include_worktree=True,
                )
                result.changed_file_count = len(changed)
            except Exception:
                result.changed_file_count = -1
            return result

        # Check worktree dirty
        if self._git and self._git.is_dirty():
            result.is_stale = True
            result.reason = "worktree_dirty"
            return result

        return result


class ReindexGuard:
    """Single-flight reindex coalescing.

    Ensures only one reindex runs at a time. If a reindex is requested
    while one is running, it sets a pending flag to run again after.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._pending = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_pending(self) -> bool:
        return self._pending

    def try_start(self) -> bool:
        """Try to start a reindex. Returns True if acquired, False if already running."""
        with self._lock:
            if self._running:
                self._pending = True
                return False
            self._running = True
            self._pending = False
            return True

    def finish(self) -> bool:
        """Finish a reindex. Returns True if another is pending."""
        with self._lock:
            self._running = False
            pending = self._pending
            self._pending = False
            return pending

    def should_block(
        self,
        staleness: StalenessResult,
        max_seconds: float = 2.0,
        max_files: int = 5,
    ) -> bool:
        """Determine if the caller should block for reindex to complete.

        Returns True when the staleness is small enough that waiting
        for an inline reindex is worthwhile.
        """
        if not staleness.is_stale:
            return False
        if staleness.changed_file_count > max_files:
            return False
        return True
