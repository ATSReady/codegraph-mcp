"""Tests for the git file watcher."""
import time

import pytest
from unittest.mock import MagicMock

from codegraph.infrastructure.watchers.git_watcher import GitWatcher


class TestGitWatcher:
    def test_start_and_stop(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (tmp_path / ".git" / "index").write_bytes(b"\x00")

        watcher = GitWatcher(str(tmp_path), poll_interval=0.1)
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_start_is_idempotent(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (tmp_path / ".git" / "index").write_bytes(b"\x00")

        watcher = GitWatcher(str(tmp_path), poll_interval=0.1)
        watcher.start()
        thread1 = watcher._thread
        watcher.start()  # second start should be no-op
        assert watcher._thread is thread1
        watcher.stop()

    def test_detects_change(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (tmp_path / ".git" / "index").write_bytes(b"\x00")

        callback = MagicMock()
        watcher = GitWatcher(str(tmp_path), on_change=callback, poll_interval=0.1)
        watcher.start()

        time.sleep(0.15)
        # Modify HEAD to trigger change detection
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/dev\n")
        time.sleep(0.3)

        watcher.stop()
        assert callback.called

    def test_no_change_no_callback(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (tmp_path / ".git" / "index").write_bytes(b"\x00")

        callback = MagicMock()
        watcher = GitWatcher(str(tmp_path), on_change=callback, poll_interval=0.1)
        watcher.start()
        time.sleep(0.3)
        watcher.stop()
        assert not callback.called

    def test_no_git_dir(self, tmp_path):
        watcher = GitWatcher(str(tmp_path), poll_interval=0.1)
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_callback_exception_does_not_crash(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (tmp_path / ".git" / "index").write_bytes(b"\x00")

        callback = MagicMock(side_effect=RuntimeError("boom"))
        watcher = GitWatcher(str(tmp_path), on_change=callback, poll_interval=0.1)
        watcher.start()

        time.sleep(0.15)
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/dev\n")
        time.sleep(0.3)

        # Watcher should still be running despite callback exception
        assert watcher.is_running
        watcher.stop()
        assert callback.called

    def test_get_mtime_missing_file(self, tmp_path):
        watcher = GitWatcher(str(tmp_path))
        assert watcher._get_mtime("nonexistent") == 0.0
