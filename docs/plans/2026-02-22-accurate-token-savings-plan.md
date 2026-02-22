# Accurate Token Savings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace hardcoded naive token baselines with data-driven calculations using actual file sizes from the index.

**Architecture:** Use cases already have access to `SymbolStore.get_metadata()` which returns `IndexMetadata` containing `file_manifest: dict[str, FileManifestEntry]`. Each `FileManifestEntry` already has a `size` field (bytes from `os.stat()`). The main gap is that `file_manifest` isn't persisted to LanceDB, so it's lost on restart. We fix serialization first, then add a `RepoStats` domain type computed during indexing, and finally update each tool's `_naive_tokens` calculation to use real data.

**Tech Stack:** Python, LanceDB, pytest

---

### Task 1: Persist file_manifest in LanceDB serialization

**Files:**
- Modify: `src/codegraph/infrastructure/storage/lancedb_store.py:532-591` (`_serialize_metadata` / `_deserialize_metadata`)
- Test: `tests/unit/infrastructure/test_metadata_serialization.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/infrastructure/test_metadata_serialization.py`:

```python
"""Tests for metadata serialization round-trip."""
import pytest

from codegraph.domain.workspace import (
    FileManifestEntry,
    IndexMetadata,
    WorkspaceState,
    EmbeddingMetadata,
    ParseStatus,
)
from codegraph.infrastructure.storage.lancedb_store import (
    _serialize_metadata,
    _deserialize_metadata,
)


def _make_metadata(manifest: dict[str, FileManifestEntry] | None = None) -> IndexMetadata:
    return IndexMetadata(
        workspace_state=WorkspaceState(
            head_commit="abc123",
            index_base="abc123",
            worktree_dirty=False,
        ),
        embedding=EmbeddingMetadata(
            provider_id="none",
            model="none",
            model_revision=None,
            runtime="none",
            device="none",
            actual_dimension=0,
            requested_dimension=None,
            config_hash="",
            input_version=1,
            normalize="none",
        ),
        generation=1,
        file_manifest=manifest or {},
    )


class TestFileManifestSerialization:
    def test_round_trip_with_manifest(self):
        manifest = {
            "src/main.py": FileManifestEntry(
                file_path="src/main.py",
                language="python",
                mtime=1234567890.0,
                size=1500,
                parse_status=ParseStatus.OK,
            ),
            "src/utils.py": FileManifestEntry(
                file_path="src/utils.py",
                language="python",
                mtime=1234567891.0,
                size=800,
                parse_status=ParseStatus.WARN,
            ),
        }
        meta = _make_metadata(manifest)
        data = _serialize_metadata(meta)
        restored = _deserialize_metadata(data)

        assert len(restored.file_manifest) == 2
        assert restored.file_manifest["src/main.py"].size == 1500
        assert restored.file_manifest["src/utils.py"].size == 800
        assert restored.file_manifest["src/utils.py"].parse_status == ParseStatus.WARN

    def test_round_trip_empty_manifest(self):
        meta = _make_metadata({})
        data = _serialize_metadata(meta)
        restored = _deserialize_metadata(data)
        assert restored.file_manifest == {}

    def test_deserialize_missing_manifest_field(self):
        """Old serialized data without file_manifest should deserialize cleanly."""
        meta = _make_metadata()
        data = _serialize_metadata(meta)
        data.pop("file_manifest", None)
        restored = _deserialize_metadata(data)
        assert restored.file_manifest == {}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/infrastructure/test_metadata_serialization.py -v`
Expected: FAIL — `file_manifest` not in serialized data, restored manifest is empty when it shouldn't be

**Step 3: Implement serialization**

In `src/codegraph/infrastructure/storage/lancedb_store.py`, update `_serialize_metadata` (after the `"package_roots"` key, before the closing `}`):

```python
        "file_manifest": {
            fp: {
                "file_path": entry.file_path,
                "language": entry.language,
                "mtime": entry.mtime,
                "size": entry.size,
                "parse_status": entry.parse_status.value,
            }
            for fp, entry in meta.file_manifest.items()
        },
```

Update `_deserialize_metadata` (after `package_roots` reconstruction):

```python
        file_manifest={
            fp: FileManifestEntry(
                file_path=d["file_path"],
                language=d["language"],
                mtime=d["mtime"],
                size=d["size"],
                parse_status=ParseStatus(d["parse_status"]),
            )
            for fp, d in data.get("file_manifest", {}).items()
        },
```

Add `FileManifestEntry` and `ParseStatus` to the imports from `codegraph.domain.workspace`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/infrastructure/test_metadata_serialization.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add src/codegraph/infrastructure/storage/lancedb_store.py tests/unit/infrastructure/test_metadata_serialization.py
git commit -m "Persist file_manifest in LanceDB metadata serialization"
```

---

### Task 2: Add RepoStats domain type and compute during indexing

**Files:**
- Modify: `src/codegraph/domain/workspace.py:60-75` (add `RepoStats` to `IndexMetadata`)
- Modify: `src/codegraph/application/index_repo.py:142-170` (compute stats after building manifest)
- Modify: `src/codegraph/infrastructure/storage/lancedb_store.py:532-591` (serialize/deserialize `repo_stats`)
- Test: `tests/unit/domain/test_repo_stats.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/domain/test_repo_stats.py`:

```python
"""Tests for RepoStats computation."""
import math
import pytest

from codegraph.domain.workspace import FileManifestEntry, ParseStatus, RepoStats


class TestRepoStatsFromManifest:
    def test_basic_computation(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 400, ParseStatus.OK),
            "b.py": FileManifestEntry("b.py", "python", 0.0, 1200, ParseStatus.OK),
            "c.py": FileManifestEntry("c.py", "python", 0.0, 800, ParseStatus.OK),
        }
        stats = RepoStats.from_manifest(manifest)

        assert stats.total_files == 3
        assert stats.total_bytes == 2400
        # tokens = ceil(bytes * 0.75)
        assert stats.total_tokens == math.ceil(2400 * 0.75)
        assert len(stats.per_file_tokens) == 3
        assert stats.per_file_tokens["a.py"] == math.ceil(400 * 0.75)
        assert stats.per_file_tokens["b.py"] == math.ceil(1200 * 0.75)

    def test_median_and_percentiles(self):
        manifest = {
            f"f{i}.py": FileManifestEntry(f"f{i}.py", "python", 0.0, size, ParseStatus.OK)
            for i, size in enumerate([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])
        }
        stats = RepoStats.from_manifest(manifest)
        assert stats.total_files == 10
        # Median of 10 items = avg of 5th and 6th = (500+600)/2 = 550 bytes
        assert stats.median_file_tokens == math.ceil(550 * 0.75)

    def test_empty_manifest(self):
        stats = RepoStats.from_manifest({})
        assert stats.total_files == 0
        assert stats.total_tokens == 0
        assert stats.per_file_tokens == {}
        assert stats.median_file_tokens == 0

    def test_single_file(self):
        manifest = {
            "only.py": FileManifestEntry("only.py", "python", 0.0, 600, ParseStatus.OK),
        }
        stats = RepoStats.from_manifest(manifest)
        assert stats.total_files == 1
        assert stats.median_file_tokens == math.ceil(600 * 0.75)
        assert stats.p75_file_tokens == math.ceil(600 * 0.75)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_repo_stats.py -v`
Expected: FAIL — `RepoStats` doesn't exist yet

**Step 3: Add RepoStats to domain**

In `src/codegraph/domain/workspace.py`, add before `IndexMetadata`:

```python
import math
import statistics
from codegraph.domain.metrics import TOKEN_FACTOR


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
    def from_manifest(cls, manifest: dict[str, "FileManifestEntry"]) -> "RepoStats":
        if not manifest:
            return cls(
                total_files=0, total_bytes=0, total_tokens=0,
                median_file_tokens=0, p75_file_tokens=0, p90_file_tokens=0,
                per_file_tokens={},
            )
        sizes = [entry.size for entry in manifest.values()]
        per_file = {fp: math.ceil(entry.size * TOKEN_FACTOR) for fp, entry in manifest.items()}
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
```

Add `repo_stats` field to `IndexMetadata`:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_repo_stats.py -v`
Expected: PASS

**Step 5: Compute RepoStats during indexing**

In `src/codegraph/application/index_repo.py`, after `file_manifest=manifest,` in the `IndexMetadata` constructor (around line 170), add:

```python
        from codegraph.domain.workspace import RepoStats
        repo_stats = RepoStats.from_manifest(manifest)

        new_metadata = IndexMetadata(
            workspace_state=workspace_state,
            embedding=embedding_meta,
            generation=generation,
            file_manifest=manifest,
            repo_stats=repo_stats,
        )
```

**Step 6: Serialize RepoStats in LanceDB**

In `_serialize_metadata`, add after `"file_manifest"`:

```python
        "repo_stats": {
            "total_files": meta.repo_stats.total_files,
            "total_bytes": meta.repo_stats.total_bytes,
            "total_tokens": meta.repo_stats.total_tokens,
            "median_file_tokens": meta.repo_stats.median_file_tokens,
            "p75_file_tokens": meta.repo_stats.p75_file_tokens,
            "p90_file_tokens": meta.repo_stats.p90_file_tokens,
            "per_file_tokens": meta.repo_stats.per_file_tokens,
        } if meta.repo_stats else None,
```

In `_deserialize_metadata`, add `RepoStats` to imports and reconstruct:

```python
        rs_data = data.get("repo_stats")
        repo_stats = RepoStats(**rs_data) if rs_data else None
```

Pass `repo_stats=repo_stats` to the `IndexMetadata` constructor.

**Step 7: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests pass

**Step 8: Commit**

```bash
git add src/codegraph/domain/workspace.py src/codegraph/application/index_repo.py src/codegraph/infrastructure/storage/lancedb_store.py tests/unit/domain/test_repo_stats.py
git commit -m "Add RepoStats computed from file manifest during indexing"
```

---

### Task 3: Update file-specific tools to use actual file sizes

**Files:**
- Modify: `src/codegraph/application/tools/get_file_summary.py` (entire file, 39 lines)
- Modify: `src/codegraph/application/tools/get_symbols.py` (line 37-39)
- Modify: `src/codegraph/application/tools/get_symbol.py` (line 31)
- Modify: `src/codegraph/application/tools/get_imports.py` (line 38)
- Modify: `src/codegraph/application/tools/get_snippet.py` (line 42 — already accurate, no change needed)
- Test: `tests/unit/application/test_naive_tokens_file_tools.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/application/test_naive_tokens_file_tools.py`:

```python
"""Tests for file-specific tool naive token calculations."""
import math
from unittest.mock import MagicMock

import pytest

from codegraph.domain.metrics import TOKEN_FACTOR
from codegraph.domain.models import Symbol, SymbolKind, Edge, EdgeKind
from codegraph.domain.workspace import (
    FileManifestEntry,
    IndexMetadata,
    WorkspaceState,
    EmbeddingMetadata,
    ParseStatus,
    RepoStats,
)
from codegraph.application.tools.get_file_summary import GetFileSummaryUseCase
from codegraph.application.tools.get_symbols import GetSymbolsUseCase
from codegraph.application.tools.get_imports import GetImportsUseCase


def _make_store(manifest: dict[str, FileManifestEntry], symbols=None, edges=None):
    store = MagicMock()
    stats = RepoStats.from_manifest(manifest)
    metadata = IndexMetadata(
        workspace_state=WorkspaceState("abc", "abc", False),
        embedding=MagicMock(),
        generation=1,
        file_manifest=manifest,
        repo_stats=stats,
    )
    store.get_metadata.return_value = metadata
    store.query_symbols.return_value = (symbols or [], None)
    store.get_edges.return_value = (edges or [], None)
    return store


class TestGetFileSummaryNaiveTokens:
    def test_uses_actual_file_size(self):
        manifest = {
            "src/small.py": FileManifestEntry("src/small.py", "python", 0.0, 200, ParseStatus.OK),
        }
        store = _make_store(manifest)
        result = GetFileSummaryUseCase(store).execute(file_path="src/small.py")
        expected = math.ceil(200 * TOKEN_FACTOR)
        assert result["_naive_tokens"] == expected

    def test_falls_back_for_unknown_file(self):
        store = _make_store({})
        result = GetFileSummaryUseCase(store).execute(file_path="unknown.py")
        # Should use a reasonable fallback, not max(500, symbols * 200)
        assert result["_naive_tokens"] >= 0


class TestGetSymbolsNaiveTokens:
    def test_uses_actual_file_size_when_file_path_given(self):
        manifest = {
            "src/main.py": FileManifestEntry("src/main.py", "python", 0.0, 600, ParseStatus.OK),
        }
        store = _make_store(manifest)
        result = GetSymbolsUseCase(store).execute(file_path="src/main.py")
        expected = math.ceil(600 * TOKEN_FACTOR)
        assert result["_naive_tokens"] == expected

    def test_uses_total_tokens_when_no_file_path(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 400, ParseStatus.OK),
            "b.py": FileManifestEntry("b.py", "python", 0.0, 600, ParseStatus.OK),
        }
        store = _make_store(manifest)
        result = GetSymbolsUseCase(store).execute()
        expected = math.ceil(1000 * TOKEN_FACTOR)
        assert result["_naive_tokens"] == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/application/test_naive_tokens_file_tools.py -v`
Expected: FAIL — tools still use hardcoded formulas

**Step 3: Add helper to look up file tokens**

In each tool, add a helper method or inline the lookup. The pattern for all file-specific tools:

```python
def _get_naive_tokens(self, file_path: str) -> int:
    """Get naive token baseline from actual file size in index."""
    meta = self._store.get_metadata()
    if meta and meta.repo_stats and file_path in meta.repo_stats.per_file_tokens:
        return meta.repo_stats.per_file_tokens[file_path]
    # Fallback: use median file size or 0
    if meta and meta.repo_stats:
        return meta.repo_stats.median_file_tokens
    return 0
```

**Update `get_file_summary.py`:**
Replace `"_naive_tokens": max(500, len(symbols) * 200)` with `"_naive_tokens": self._get_naive_tokens(file_path)`.

**Update `get_symbols.py`:**
Replace the `if file_path:` / `else:` naive_tokens block:
- When `file_path` given: `self._get_naive_tokens(file_path)`
- When no `file_path`: use `meta.repo_stats.total_tokens` (reading all files)

**Update `get_symbol.py`:**
Replace `"_naive_tokens": 3000` with lookup of the symbol's `file_path`.

**Update `get_imports.py`:**
Replace `max(500, len(edges) * 150)` with `self._get_naive_tokens(file_path)` when `file_path` is provided, otherwise use median.

**Note:** `get_snippet.py` already uses `estimate_tokens("".join(all_lines))` which reads the actual file — no change needed.

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/application/test_naive_tokens_file_tools.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass (some existing naive token assertions in other tests may need updating)

**Step 6: Commit**

```bash
git add src/codegraph/application/tools/get_file_summary.py src/codegraph/application/tools/get_symbols.py src/codegraph/application/tools/get_symbol.py src/codegraph/application/tools/get_imports.py tests/unit/application/test_naive_tokens_file_tools.py
git commit -m "Update file-specific tools to use actual file sizes for naive baselines"
```

---

### Task 4: Update search/graph tools to use actual file sizes

**Files:**
- Modify: `src/codegraph/application/tools/semantic_search.py` (line 55)
- Modify: `src/codegraph/application/tools/find_references.py` (line 32)
- Modify: `src/codegraph/application/tools/get_dependents.py` (line 29)
- Modify: `src/codegraph/application/tools/get_call_graph.py` (line 39)
- Modify: `src/codegraph/application/tools/get_hierarchy.py` (line 39)
- Modify: `src/codegraph/application/tools/resolve_symbol.py` (line 40)
- Test: `tests/unit/application/test_naive_tokens_search_tools.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/application/test_naive_tokens_search_tools.py`:

```python
"""Tests for search/graph tool naive token calculations."""
import math
from unittest.mock import MagicMock

import pytest

from codegraph.domain.metrics import TOKEN_FACTOR
from codegraph.domain.models import Edge, EdgeKind
from codegraph.domain.workspace import (
    FileManifestEntry,
    IndexMetadata,
    WorkspaceState,
    ParseStatus,
    RepoStats,
)
from codegraph.application.tools.find_references import FindReferencesUseCase
from codegraph.application.tools.get_dependents import GetDependentsUseCase
from codegraph.application.tools.get_call_graph import GetCallGraphUseCase


def _make_edge(file_path: str, kind: EdgeKind = EdgeKind.CALLS) -> Edge:
    return Edge(
        source_symbol_id="src_id",
        kind=kind,
        file_path=file_path,
        start_line=1,
        end_line=10,
        column=0,
        ref_text="ref",
        target_symbol_id="tgt_id",
    )


def _make_store(manifest, edges=None):
    store = MagicMock()
    stats = RepoStats.from_manifest(manifest)
    metadata = IndexMetadata(
        workspace_state=WorkspaceState("abc", "abc", False),
        embedding=MagicMock(),
        generation=1,
        file_manifest=manifest,
        repo_stats=stats,
    )
    store.get_metadata.return_value = metadata
    store.get_edges.return_value = (edges or [], None)
    return store


class TestFindReferencesNaiveTokens:
    def test_uses_sum_of_referenced_file_sizes(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 400, ParseStatus.OK),
            "b.py": FileManifestEntry("b.py", "python", 0.0, 600, ParseStatus.OK),
            "c.py": FileManifestEntry("c.py", "python", 0.0, 200, ParseStatus.OK),
        }
        edges = [_make_edge("a.py"), _make_edge("b.py")]
        store = _make_store(manifest, edges)
        result = FindReferencesUseCase(store).execute(symbol_id="some_id")
        # Naive = sum of unique file sizes referenced
        expected = math.ceil(400 * TOKEN_FACTOR) + math.ceil(600 * TOKEN_FACTOR)
        assert result["_naive_tokens"] == expected

    def test_deduplicates_files(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 400, ParseStatus.OK),
        }
        edges = [_make_edge("a.py"), _make_edge("a.py")]
        store = _make_store(manifest, edges)
        result = FindReferencesUseCase(store).execute(symbol_id="some_id")
        expected = math.ceil(400 * TOKEN_FACTOR)
        assert result["_naive_tokens"] == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/application/test_naive_tokens_search_tools.py -v`
Expected: FAIL

**Step 3: Update search/graph tools**

The pattern for all edge-based tools — compute naive tokens as sum of unique file sizes:

```python
def _get_naive_from_edges(self, edges: list) -> int:
    """Naive baseline = sum of token costs of unique files containing edges."""
    meta = self._store.get_metadata()
    if not meta or not meta.repo_stats:
        return 0
    unique_files = {e.file_path for e in edges}
    return sum(
        meta.repo_stats.per_file_tokens.get(fp, 0)
        for fp in unique_files
    )
```

Apply this pattern to:
- `find_references.py`: Replace `max(2000, len(edges) * 500)` with `self._get_naive_from_edges(edges)`
- `get_dependents.py`: Replace `max(2000, len(edges) * 500)` with `self._get_naive_from_edges(edges)`
- `get_call_graph.py`: Replace `max(2000, len(edges) * 500)` with `self._get_naive_from_edges(edges)`
- `get_hierarchy.py`: Replace `max(2000, len(edges) * 500)` with `self._get_naive_from_edges(edges)`

For `resolve_symbol.py`: Replace `max(2000, len(matches) * 400)` with sum of unique file sizes from matched symbols:

```python
meta = self._store.get_metadata()
if meta and meta.repo_stats:
    unique_files = {s.file_path for s in matches}
    naive = sum(meta.repo_stats.per_file_tokens.get(fp, 0) for fp in unique_files)
else:
    naive = 0
```

For `semantic_search.py`: Replace `max(3000, len(results) * 800)` with sum of unique file sizes from result chunks:

```python
meta = self._store.get_metadata()
if meta and meta.repo_stats:
    unique_files = {r.file_path for r in results}
    naive = sum(meta.repo_stats.per_file_tokens.get(fp, 0) for fp in unique_files)
else:
    naive = 0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/application/test_naive_tokens_search_tools.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/codegraph/application/tools/semantic_search.py src/codegraph/application/tools/find_references.py src/codegraph/application/tools/get_dependents.py src/codegraph/application/tools/get_call_graph.py src/codegraph/application/tools/get_hierarchy.py src/codegraph/application/tools/resolve_symbol.py tests/unit/application/test_naive_tokens_search_tools.py
git commit -m "Update search/graph tools to use actual file sizes for naive baselines"
```

---

### Task 5: Update get_repo_overview to report RepoStats

**Files:**
- Modify: `src/codegraph/application/tools/get_repo_overview.py` (lines 27-37)
- Test: `tests/unit/application/test_repo_overview_stats.py` (create)

**Step 1: Write the failing test**

Create `tests/unit/application/test_repo_overview_stats.py`:

```python
"""Tests for repo overview including RepoStats."""
import math
from unittest.mock import MagicMock

from codegraph.domain.workspace import (
    FileManifestEntry,
    IndexMetadata,
    WorkspaceState,
    ParseStatus,
    RepoStats,
)
from codegraph.application.tools.get_repo_overview import GetRepoOverviewUseCase


class TestRepoOverviewStats:
    def test_includes_repo_stats(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 400, ParseStatus.OK),
            "b.py": FileManifestEntry("b.py", "python", 0.0, 600, ParseStatus.OK),
        }
        stats = RepoStats.from_manifest(manifest)
        metadata = IndexMetadata(
            workspace_state=WorkspaceState("abc", "abc", False),
            embedding=MagicMock(),
            generation=1,
            file_manifest=manifest,
            repo_stats=stats,
        )
        store = MagicMock()
        store.get_metadata.return_value = metadata
        result = GetRepoOverviewUseCase(store).execute()

        assert result["total_tokens"] == stats.total_tokens
        assert result["median_file_tokens"] == stats.median_file_tokens
        assert result["_naive_tokens"] == stats.total_tokens
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/application/test_repo_overview_stats.py -v`
Expected: FAIL — `total_tokens` not in result

**Step 3: Update get_repo_overview.py**

Add repo stats fields to the result dict and set `_naive_tokens` to `total_tokens`:

```python
        if metadata:
            result.update({
                "generation": metadata.generation,
                "head_commit": metadata.workspace_state.head_commit,
                "file_count": len(metadata.file_manifest),
                "embedding_provider": metadata.embedding.provider_id,
                "embedding_model": metadata.embedding.model,
            })
            if metadata.repo_stats:
                result.update({
                    "total_tokens": metadata.repo_stats.total_tokens,
                    "median_file_tokens": metadata.repo_stats.median_file_tokens,
                    "p75_file_tokens": metadata.repo_stats.p75_file_tokens,
                })
```

Set `_naive_tokens`:
```python
        if metadata and metadata.repo_stats:
            result["_naive_tokens"] = metadata.repo_stats.total_tokens
        else:
            result["_naive_tokens"] = 0
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/application/test_repo_overview_stats.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/codegraph/application/tools/get_repo_overview.py tests/unit/application/test_repo_overview_stats.py
git commit -m "Add RepoStats to repo overview and use total_tokens as naive baseline"
```

---

### Task 6: Update existing tests and clean up

**Files:**
- Modify: `tests/unit/application/test_naive_estimation.py` (update assertions)
- Modify: `tests/integration/test_metrics_flow.py` (may need fixture updates)
- Review: Any test that asserts specific `_naive_tokens` values

**Step 1: Run full test suite and fix any failures**

Run: `pytest tests/ -v`

For each failure: update the test to either mock `get_metadata()` with a proper manifest, or adjust expected naive token values to match the new data-driven calculations.

**Step 2: Commit**

```bash
git add -u tests/
git commit -m "Update tests for data-driven token savings estimation"
```

---

### Task 7: Integration test — index a repo, call tools, verify plausible savings

**Files:**
- Modify: `tests/integration/test_metrics_flow.py` (extend existing test)

**Step 1: Write the integration test**

Add to `tests/integration/test_metrics_flow.py`:

```python
class TestAccurateTokenSavings:
    def test_savings_are_plausible(self, indexed_repo):
        """After indexing, tool savings should reflect actual file sizes."""
        store, repo_root = indexed_repo

        # Call get_file_summary on a known file
        from codegraph.application.tools.get_file_summary import GetFileSummaryUseCase
        result = GetFileSummaryUseCase(store).execute(file_path="src/main.py")

        naive = result["_naive_tokens"]
        # Naive should be based on actual file size, not hardcoded 500+
        # For a typical small file, should be < 1000, not 2400
        metadata = store.get_metadata()
        if metadata and "src/main.py" in metadata.file_manifest:
            actual_size = metadata.file_manifest["src/main.py"].size
            expected = math.ceil(actual_size * 0.75)
            assert naive == expected

    def test_repo_stats_computed(self, indexed_repo):
        """RepoStats should be populated after indexing."""
        store, _ = indexed_repo
        metadata = store.get_metadata()
        assert metadata is not None
        assert metadata.repo_stats is not None
        assert metadata.repo_stats.total_files > 0
        assert metadata.repo_stats.total_tokens > 0
        assert len(metadata.repo_stats.per_file_tokens) == metadata.repo_stats.total_files
```

**Step 2: Run test**

Run: `pytest tests/integration/test_metrics_flow.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_metrics_flow.py
git commit -m "Add integration tests verifying plausible token savings from index data"
```

---

### Task 8: Final verification and reindex

**Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All pass

**Step 2: Reindex the codegraph repo itself**

Run: `codegraph index`

**Step 3: Call a tool and verify savings look reasonable**

Run: `codegraph status`

Check that `session_tokens_saved` numbers are lower and more realistic than before.

**Step 4: Commit any remaining changes**

```bash
git add -A
git commit -m "Final cleanup for accurate token savings"
```
