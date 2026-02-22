"""Workspace state, metadata, and diagnostic types."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from codegraph.domain.metrics import TOKEN_FACTOR


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
class RepoStats:
    """Computed repository statistics for accurate token savings estimation."""

    total_files: int
    total_bytes: int
    total_tokens: int
    median_file_tokens: int
    p75_file_tokens: int
    p90_file_tokens: int
    per_file_tokens: dict[str, int]

    @classmethod
    def from_manifest(cls, manifest: dict[str, FileManifestEntry]) -> RepoStats:
        if not manifest:
            return cls(
                total_files=0,
                total_bytes=0,
                total_tokens=0,
                median_file_tokens=0,
                p75_file_tokens=0,
                p90_file_tokens=0,
                per_file_tokens={},
            )
        sizes = [entry.size for entry in manifest.values()]
        per_file = {
            fp: math.ceil(entry.size * TOKEN_FACTOR)
            for fp, entry in manifest.items()
        }
        total_bytes = sum(sizes)
        sorted_sizes = sorted(sizes)
        n = len(sorted_sizes)

        def _percentile(data: list[int], pct: float) -> int:
            """Linear interpolation percentile."""
            if len(data) == 1:
                return math.ceil(data[0] * TOKEN_FACTOR)
            k = (pct / 100) * (len(data) - 1)
            f = int(k)
            c = f + 1 if f + 1 < len(data) else f
            d = k - f
            val = data[f] + d * (data[c] - data[f])
            return math.ceil(val * TOKEN_FACTOR)

        return cls(
            total_files=n,
            total_bytes=total_bytes,
            total_tokens=math.ceil(total_bytes * TOKEN_FACTOR),
            median_file_tokens=_percentile(sorted_sizes, 50),
            p75_file_tokens=_percentile(sorted_sizes, 75),
            p90_file_tokens=_percentile(sorted_sizes, 90),
            per_file_tokens=per_file,
        )


@dataclass
class IndexMetadata:
    workspace_state: WorkspaceState
    embedding: EmbeddingMetadata
    generation: int
    package_roots: list[PackageRoot] = field(default_factory=list)
    file_manifest: dict[str, FileManifestEntry] = field(default_factory=dict)
    module_path_rules: list[dict] = field(default_factory=list)
    module_path_cache: dict[str, str] = field(default_factory=dict)
    repo_stats: Optional[RepoStats] = None
