"""Configuration types. Pure data, loaded by infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IndexConfig:
    exclude: list[str] = field(default_factory=lambda: [
        "vendor/**", "generated/**", "**/*.min.js",
    ])
    include_uses: bool = False
    languages: list[str] = field(default_factory=list)


@dataclass
class ServerConfig:
    check_interval: int = 60
    auto_reindex: bool = True
    log_level: str = "info"
    log_file: str = "server.log"
    log_max_size_mb: int = 10
    log_keep_rotations: int = 3
    max_blocking_reindex_seconds: float = 2.0
    max_blocking_reindex_files: int = 5


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: Optional[str] = None
    normalize_vectors: bool = True
    auto_reembed_on_change: bool = False
    batch_size: int = 64
    gpu_concurrency: int = 1
    cpu_concurrency: int = 1
    cpu_threads: int = 0
    dimension: Optional[int] = None
    api_key_env: Optional[str] = None
    max_concurrent_requests: int = 4


@dataclass
class PathsConfig:
    index_dir: str = ".codegraph/index.lance"
    repo_root: str = "auto"


@dataclass
class CompactionConfig:
    auto_compact_interval: int = 10
    keep_generations: int = 3


@dataclass
class CodegraphConfig:
    index: IndexConfig = field(default_factory=IndexConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    compaction: CompactionConfig = field(default_factory=CompactionConfig)
