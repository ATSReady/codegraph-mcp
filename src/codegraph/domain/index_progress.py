from dataclasses import dataclass, field
from enum import Enum


class ProgressState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMMITTING = "committing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class IndexProgressSnapshot:
    operation_id: str
    mode: str
    state: ProgressState = ProgressState.QUEUED
    partitions_total: int = 0
    files_total: int = 0
    partitions_done: int = 0
    files_done: int = 0
    files_failed: int = 0
    current_partition: str | None = None
    current_file: str | None = None
    errors: list[str] = field(default_factory=list)
