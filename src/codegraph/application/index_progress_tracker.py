from __future__ import annotations

from copy import deepcopy
from threading import Lock
from uuid import uuid4

from codegraph.domain.index_progress import IndexProgressSnapshot, ProgressState


class IndexProgressTracker:
    def __init__(self, max_errors: int = 20) -> None:
        self._lock = Lock()
        self._max_errors = max_errors
        self._snapshots: dict[str, IndexProgressSnapshot] = {}
        self._active_operation_id: str | None = None
        self._last_operation_id: str | None = None

    def start(self, mode: str, partitions_total: int = 0, files_total: int = 0) -> str:
        operation_id = str(uuid4())
        snapshot = IndexProgressSnapshot(
            operation_id=operation_id,
            mode=mode,
            partitions_total=max(0, partitions_total),
            files_total=max(0, files_total),
            state=ProgressState.QUEUED,
        )
        with self._lock:
            self._snapshots[operation_id] = snapshot
            self._active_operation_id = operation_id
            self._last_operation_id = operation_id
        return operation_id

    def get(self, operation_id: str) -> IndexProgressSnapshot | None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            return deepcopy(snapshot) if snapshot is not None else None

    def get_active(self) -> IndexProgressSnapshot | None:
        with self._lock:
            if self._active_operation_id is None:
                return None
            snapshot = self._snapshots.get(self._active_operation_id)
            return deepcopy(snapshot) if snapshot is not None else None

    def get_last(self) -> IndexProgressSnapshot | None:
        with self._lock:
            if self._last_operation_id is None:
                return None
            snapshot = self._snapshots.get(self._last_operation_id)
            return deepcopy(snapshot) if snapshot is not None else None

    def set_state(self, operation_id: str, state: ProgressState) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.state = state

    def mark_partition_started(self, operation_id: str, partition: str) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.current_partition = partition

    def mark_partition_done(self, operation_id: str) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.partitions_done += 1
            snapshot.current_partition = None

    def mark_file_started(self, operation_id: str, file_path: str) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.current_file = file_path

    def mark_file_done(self, operation_id: str) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.files_done += 1
            snapshot.current_file = None

    def mark_file_failed(self, operation_id: str, error: str | None = None) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.files_failed += 1
            snapshot.current_file = None
            if error:
                snapshot.errors.append(error)
                if len(snapshot.errors) > self._max_errors:
                    snapshot.errors = snapshot.errors[-self._max_errors :]

    def complete(self, operation_id: str) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.state = ProgressState.COMPLETED
            if self._active_operation_id == operation_id:
                self._active_operation_id = None

    def fail(self, operation_id: str, error: str | None = None) -> None:
        with self._lock:
            snapshot = self._snapshots.get(operation_id)
            if snapshot is None:
                return
            snapshot.state = ProgressState.FAILED
            if error:
                snapshot.errors.append(error)
                if len(snapshot.errors) > self._max_errors:
                    snapshot.errors = snapshot.errors[-self._max_errors :]
            if self._active_operation_id == operation_id:
                self._active_operation_id = None
