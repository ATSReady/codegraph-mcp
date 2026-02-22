import json
import os
import time
import pytest
from codegraph.infrastructure.storage.lock import IndexLock, LockInfo


class TestIndexLock:
    def test_acquire_and_release(self, tmp_path):
        lock = IndexLock(str(tmp_path / "index.lock"))
        assert lock.acquire()
        assert lock.is_locked()
        lock.release()
        assert not lock.is_locked()

    def test_double_acquire_fails(self, tmp_path):
        lock = IndexLock(str(tmp_path / "index.lock"))
        assert lock.acquire()
        lock2 = IndexLock(str(tmp_path / "index.lock"))
        assert not lock2.acquire()
        lock.release()

    def test_lock_info(self, tmp_path):
        lock = IndexLock(str(tmp_path / "index.lock"))
        lock.acquire()
        info = lock.read_lock_info()
        assert info is not None
        assert info.pid == os.getpid()
        assert info.hostname is not None
        lock.release()

    def test_break_stale_lock_dead_pid(self, tmp_path):
        lock_path = str(tmp_path / "index.lock")
        import socket
        info = {
            "pid": 999999999,
            "hostname": socket.gethostname(),
            "user": os.environ.get("USER", "unknown"),
            "acquired_at": "2026-02-22T14:30:12Z",
            "command": "codegraph index",
        }
        with open(lock_path, "w") as f:
            json.dump(info, f)

        lock = IndexLock(lock_path)
        assert lock.is_locked()
        assert lock.break_if_stale(stale_after_seconds=3600)
        assert not lock.is_locked()

    def test_break_stale_lock_by_age(self, tmp_path):
        lock_path = str(tmp_path / "index.lock")
        info = {
            "pid": os.getpid(),
            "hostname": "other-host",
            "user": "someone",
            "acquired_at": "2020-01-01T00:00:00Z",
            "command": "codegraph index",
        }
        with open(lock_path, "w") as f:
            json.dump(info, f)

        lock = IndexLock(lock_path)
        assert lock.is_locked()
        assert lock.break_if_stale(stale_after_seconds=60)

    def test_context_manager(self, tmp_path):
        lock = IndexLock(str(tmp_path / "index.lock"))
        with lock:
            assert lock.is_locked()
        assert not lock.is_locked()

    def test_context_manager_raises_on_locked(self, tmp_path):
        """Context manager raises IndexLockedError when lock is held."""
        from codegraph.domain.errors import IndexLockedError
        lock_path = str(tmp_path / "index.lock")
        lock1 = IndexLock(lock_path)
        lock1.acquire()
        lock2 = IndexLock(lock_path)
        with pytest.raises(IndexLockedError):
            with lock2:
                pass
        lock1.release()
