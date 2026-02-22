"""File-based index lock to prevent concurrent writes."""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from codegraph.domain.errors import IndexLockedError


@dataclass
class LockInfo:
    pid: int
    hostname: str
    user: str
    acquired_at: str
    command: str


class IndexLock:
    """File-based lock for index write operations."""

    def __init__(self, lock_path: str) -> None:
        self._path = Path(lock_path)
        self._held = False

    def acquire(self) -> bool:
        if self._path.exists():
            return False
        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            info = {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "user": os.environ.get("USER", "unknown"),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                "command": "codegraph index",
            }
            os.write(fd, json.dumps(info, indent=2).encode())
            os.close(fd)
            self._held = True
            return True
        except FileExistsError:
            return False

    def release(self) -> None:
        if self._path.exists():
            self._path.unlink(missing_ok=True)
        self._held = False

    def is_locked(self) -> bool:
        return self._path.exists()

    def read_lock_info(self) -> Optional[LockInfo]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            return LockInfo(**data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def break_if_stale(self, stale_after_seconds: int = 3600) -> bool:
        """Break lock if holder is dead or lock is old enough."""
        info = self.read_lock_info()
        if info is None:
            if self._path.exists():
                self._path.unlink(missing_ok=True)
                return True
            return True

        if info.hostname == socket.gethostname():
            try:
                os.kill(info.pid, 0)
            except OSError:
                self._path.unlink(missing_ok=True)
                return True

        try:
            acquired = datetime.fromisoformat(info.acquired_at)
            age = (datetime.now(timezone.utc) - acquired).total_seconds()
            if age > stale_after_seconds:
                self._path.unlink(missing_ok=True)
                return True
        except (ValueError, TypeError):
            self._path.unlink(missing_ok=True)
            return True

        return False

    def __enter__(self) -> IndexLock:
        if not self.acquire():
            info = self.read_lock_info()
            if not info:
                raise IndexLockedError(pid=-1, hostname="unknown")
            raise IndexLockedError(pid=info.pid, hostname=info.hostname)
        return self

    def __exit__(self, *args) -> None:
        self.release()
