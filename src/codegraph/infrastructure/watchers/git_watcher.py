"""File system watcher for git state changes."""
from __future__ import annotations

import logging
import time
import threading
from pathlib import Path
from typing import Callable, Optional


logger = logging.getLogger("codegraph.watcher")


class GitWatcher:
    """Watches .git/HEAD and .git/index for changes to trigger reindex."""

    def __init__(
        self,
        repo_root: str,
        on_change: Optional[Callable] = None,
        poll_interval: float = 2.0,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._on_change = on_change
        self._poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._head_mtime: float = 0.0
        self._index_mtime: float = 0.0

    def start(self) -> None:
        """Start watching for git state changes in a background thread."""
        if self._running:
            return
        self._running = True
        self._head_mtime = self._get_mtime(".git/HEAD")
        self._index_mtime = self._get_mtime(".git/index")
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Git watcher started for %s", self._repo_root)

    def stop(self) -> None:
        """Stop the watcher thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("Git watcher stopped")

    def _poll_loop(self) -> None:
        """Main polling loop that detects mtime changes on git files."""
        while self._running:
            time.sleep(self._poll_interval)
            try:
                head_mtime = self._get_mtime(".git/HEAD")
                index_mtime = self._get_mtime(".git/index")

                if head_mtime != self._head_mtime or index_mtime != self._index_mtime:
                    self._head_mtime = head_mtime
                    self._index_mtime = index_mtime
                    logger.info("Git state change detected")
                    if self._on_change:
                        try:
                            self._on_change()
                        except Exception:
                            logger.exception("Error in change callback")
            except Exception:
                logger.exception("Error polling git state")

    def _get_mtime(self, relative_path: str) -> float:
        """Get modification time for a file relative to repo root."""
        path = self._repo_root / relative_path
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    @property
    def is_running(self) -> bool:
        """Whether the watcher thread is currently active."""
        return self._running
