"""TOML configuration loader."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from codegraph.domain.config import (
    CodegraphConfig, IndexConfig, ServerConfig, EmbeddingConfig,
    PathsConfig, CompactionConfig,
)

# Grab the defaults from a fresh instance so we don't rely on class attrs
_DEFAULT_INDEX = IndexConfig()


def load_config(repo_root: str, config_path: Optional[str] = None) -> CodegraphConfig:
    """Load configuration from TOML file, falling back to defaults."""
    if config_path is None:
        config_path = os.path.join(repo_root, ".codegraph", "config.toml")
    
    if not os.path.exists(config_path):
        return CodegraphConfig()

    try:
        # Python 3.11+ has tomllib built-in
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return CodegraphConfig()

    return _parse_config(data, repo_root)


def _parse_config(data: dict, repo_root: str) -> CodegraphConfig:
    """Parse TOML dict into CodegraphConfig."""
    index_data = data.get("index", {})
    server_data = data.get("server", {})
    embedding_data = data.get("embedding", {})
    paths_data = data.get("paths", {})
    compaction_data = data.get("compaction", {})

    index = IndexConfig(
        exclude=index_data.get("exclude", _DEFAULT_INDEX.exclude),
        include_uses=index_data.get("include_uses", False),
        languages=index_data.get("languages", []),
        parallel_workers=index_data.get("parallel_workers", 0),
        partition_strategy=index_data.get("partition_strategy", "hybrid"),
        min_partition_files=index_data.get("min_partition_files", 1),
        progress_event_interval_ms=index_data.get("progress_event_interval_ms", 250),
    )

    server = ServerConfig(
        check_interval=server_data.get("check_interval", 60),
        auto_reindex=server_data.get("auto_reindex", True),
        log_level=server_data.get("log_level", "info"),
        log_file=server_data.get("log_file", "server.log"),
        log_max_size_mb=server_data.get("log_max_size_mb", 10),
        log_keep_rotations=server_data.get("log_keep_rotations", 3),
        max_blocking_reindex_seconds=server_data.get("max_blocking_reindex_seconds", 2.0),
        max_blocking_reindex_files=server_data.get("max_blocking_reindex_files", 5),
    )

    embedding = EmbeddingConfig(
        provider=embedding_data.get("provider", "local"),
        model=embedding_data.get("model"),
        normalize_vectors=embedding_data.get("normalize_vectors", True),
        auto_reembed_on_change=embedding_data.get("auto_reembed_on_change", False),
        batch_size=embedding_data.get("batch_size", 64),
        gpu_concurrency=embedding_data.get("gpu_concurrency", 1),
        cpu_concurrency=embedding_data.get("cpu_concurrency", 1),
        cpu_threads=embedding_data.get("cpu_threads", 0),
        dimension=embedding_data.get("dimension"),
        api_key_env=embedding_data.get("api_key_env"),
        max_concurrent_requests=embedding_data.get("max_concurrent_requests", 4),
    )

    paths = PathsConfig(
        index_dir=paths_data.get("index_dir", ".codegraph/index.lance"),
        repo_root=paths_data.get("repo_root", "auto"),
    )

    compaction = CompactionConfig(
        auto_compact_interval=compaction_data.get("auto_compact_interval", 10),
        keep_generations=compaction_data.get("keep_generations", 3),
    )

    return CodegraphConfig(
        index=index,
        server=server,
        embedding=embedding,
        paths=paths,
        compaction=compaction,
    )


def save_default_config(config_path: str) -> None:
    """Write a default config.toml file."""
    default = '''# codegraph configuration
# See documentation for all options.

[index]
exclude = ["vendor/**", "generated/**", "**/*.min.js", "node_modules/**"]
# include_uses = false
# languages = []  # empty = all supported
# parallel_workers = 0  # 0 = auto (uses available CPU cores)
# partition_strategy = "hybrid"
# min_partition_files = 1
# progress_event_interval_ms = 250

[server]
auto_reindex = true
log_level = "info"
# check_interval = 60
# max_blocking_reindex_seconds = 2.0
# max_blocking_reindex_files = 5

[embedding]
provider = "local"
# model = "nomic-embed-text-v1.5"
# normalize_vectors = true
# batch_size = 64

[paths]
# index_dir = ".codegraph/index.lance"
# repo_root = "auto"

[compaction]
# auto_compact_interval = 10
# keep_generations = 3
'''
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        f.write(default)
