# Accurate Token Savings Estimation

## Problem

Token savings estimates are inflated due to hardcoded naive baselines that don't reflect actual file sizes or repository characteristics. For example, `get_file_summary` assumes every file is 300 lines when many are under 100.

## Solution

Replace hardcoded baselines with data-driven calculations using file sizes already collected during indexing.

## Design

### 1. Index-Time Statistics

Compute `RepoStats` during indexing from existing `FileManifestEntry.size` data:

```python
@dataclass
class RepoStats:
    total_files: int
    total_lines: int
    total_tokens: int              # sum(file_size * 0.75) for all files
    avg_file_tokens: int
    median_file_tokens: int
    p75_file_tokens: int
    p90_file_tokens: int
    per_file_tokens: dict[str, int]  # file_path → token count
```

Stored in `IndexMetadata.repo_stats`. Recomputed on every index/reindex. No additional I/O — just math on existing data.

### 2. Per-Tool Naive Baselines

**Principle:** The naive baseline is the token cost of the files you'd need to read to get the same information without codegraph.

#### File-specific tools — baseline = actual file token count

| Tool | New Naive Baseline |
|------|-------------------|
| `get_file_summary` | `per_file_tokens[file_path]` |
| `get_symbols` | `per_file_tokens[file_path]` |
| `get_snippet` | Already correct (reads full file, computes tokens) |
| `get_symbol` | `per_file_tokens[file_path]` |
| `get_imports` | `per_file_tokens[file_path]` |

#### Search/graph tools — baseline = sum of matched file token counts

| Tool | New Naive Baseline |
|------|-------------------|
| `semantic_search` | `sum(per_file_tokens[f] for f in matched_files)` |
| `find_references` | `sum(per_file_tokens[f] for f in files_with_refs)` |
| `get_dependents` | `sum(per_file_tokens[f] for f in dependent_files)` |
| `get_call_graph` | `sum(per_file_tokens[f] for f in files_in_call_chain)` |
| `get_hierarchy` | `sum(per_file_tokens[f] for f in files_in_hierarchy)` |
| `resolve_symbol` | `sum(per_file_tokens[f] for f in candidate_files)` |

#### Repo-level tools

| Tool | New Naive Baseline |
|------|-------------------|
| `get_repo_overview` | `repo_stats.total_tokens` |
| `get_changed_files` | `0` (git status is cheap) |
| `get_diff` | Keep current git diff baseline |

### 3. Actual Response Measurement

No changes. Already works correctly: serialize response to JSON, apply `estimate_tokens()` (chars × 0.75).

### 4. Plumbing

1. Add `repo_stats: RepoStats` field to `IndexMetadata`
2. Compute `RepoStats` from `file_manifest` at end of `index_repo.py`
3. Inject `RepoStats` into each UseCase (via constructor or store access)
4. Replace hardcoded `_naive_tokens` formulas in each UseCase with `per_file_tokens` lookups
5. Serialize/deserialize `RepoStats` in LanceDB metadata table

### 5. Cleanup

Remove:
- `TOOL_BASELINES` dict with hardcoded constants (if present)
- `TokenSavingsCalculator` class (if present, replaced by `MetricsTracker`)
- `TOKENS_PER_LINE`, `FULL_FILE_AVG_LINES`, `GREP_RESULT_AVG_LINES` constants
- All `max(X, Y * Z)` patterns in use case `_naive_tokens` calculations

### 6. Testing

- Unit test: `RepoStats` computation from known file manifest
- Unit test: each tool's naive baseline uses `per_file_tokens` correctly
- Integration test: index a repo, call tools, verify savings are plausible (actual < naive, but not by 90%+)
- Regression: existing metrics persistence and display still works
