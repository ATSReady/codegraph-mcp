"""Workspace state, metadata, and diagnostic types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ParseStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERROR = "error"


@dataclass
class FileManifestEntry:
    file_path: str
    language: str
    mtime: float
    size: int
    parse_status: ParseStatus = ParseStatus.OK


@dataclass
class PackageRoot:
    language: str
    root_path: str
    rule: str


@dataclass
class FileDiagnostic:
    file_path: str
    parse_status: ParseStatus
    error_count: int
    error_spans: list[dict] = field(default_factory=list)
    indexed_at: Optional[str] = None


@dataclass
class WorkspaceState:
    head_commit: str
    index_base: str
    worktree_dirty: bool
    worktree_fingerprint: Optional[str] = None
    index_timestamp: Optional[str] = None

    def is_stale_for_commit(self, current_head: str) -> bool:
        return self.head_commit != current_head


@dataclass
class EmbeddingMetadata:
    provider_id: str
    model: str
    model_revision: Optional[str]
    runtime: str
    device: str
    actual_dimension: int
    requested_dimension: Optional[int]
    config_hash: str
    input_version: int
    normalize: str


@dataclass
class IndexMetadata:
    workspace_state: WorkspaceState
    embedding: EmbeddingMetadata
    generation: int
    package_roots: list[PackageRoot] = field(default_factory=list)
    file_manifest: dict[str, FileManifestEntry] = field(default_factory=dict)
    module_path_rules: list[dict] = field(default_factory=list)
    module_path_cache: dict[str, str] = field(default_factory=dict)
