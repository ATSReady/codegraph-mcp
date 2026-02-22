from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IndexPartition:
    root_path: str
    kind: str
    files: list[str]
    estimated_weight: int


def _top_level_root(path: str) -> str:
    if "/" not in path:
        return "."
    return path.split("/", 1)[0] or "."


def _match_submodule(path: str, submodules: list[str]) -> str | None:
    for sub in sorted(submodules, key=len, reverse=True):
        if path == sub or path.startswith(f"{sub}/"):
            return sub
    return None


def plan_partitions(
    files: list[str],
    submodules: list[str],
    min_partition_files: int = 1,
) -> list[IndexPartition]:
    buckets: dict[tuple[str, str], list[str]] = {}
    for file_path in sorted(files):
        submodule = _match_submodule(file_path, submodules)
        if submodule:
            key = (submodule, "submodule")
        else:
            key = (_top_level_root(file_path), "top_level")
        buckets.setdefault(key, []).append(file_path)

    partitions = [
        IndexPartition(
            root_path=root,
            kind=kind,
            files=members,
            estimated_weight=len(members),
        )
        for (root, kind), members in buckets.items()
    ]

    if min_partition_files > 1:
        small = [p for p in partitions if len(p.files) < min_partition_files]
        large = [p for p in partitions if len(p.files) >= min_partition_files]
        if small:
            merged_files: list[str] = []
            for p in small:
                merged_files.extend(p.files)
            large.append(
                IndexPartition(
                    root_path="__coalesced__",
                    kind="coalesced",
                    files=sorted(merged_files),
                    estimated_weight=len(merged_files),
                )
            )
        partitions = large

    return sorted(partitions, key=lambda p: (-p.estimated_weight, p.root_path))
