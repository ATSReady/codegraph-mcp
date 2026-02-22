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


class TestGetDependentsNaiveTokens:
    def test_uses_sum_of_dependent_file_sizes(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 500, ParseStatus.OK),
            "b.py": FileManifestEntry("b.py", "python", 0.0, 300, ParseStatus.OK),
        }
        edges = [_make_edge("a.py"), _make_edge("b.py")]
        store = _make_store(manifest, edges)
        result = GetDependentsUseCase(store).execute(symbol_id="some_id")
        expected = math.ceil(500 * TOKEN_FACTOR) + math.ceil(300 * TOKEN_FACTOR)
        assert result["_naive_tokens"] == expected


class TestGetCallGraphNaiveTokens:
    def test_uses_sum_of_call_file_sizes(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 800, ParseStatus.OK),
        }
        edges = [_make_edge("a.py")]
        store = _make_store(manifest, edges)
        result = GetCallGraphUseCase(store).execute(symbol_id="some_id")
        expected = math.ceil(800 * TOKEN_FACTOR)
        assert result["_naive_tokens"] == expected

    def test_no_metadata_returns_zero(self):
        store = MagicMock()
        store.get_metadata.return_value = None
        store.get_edges.return_value = ([_make_edge("a.py")], None)
        result = GetCallGraphUseCase(store).execute(symbol_id="some_id")
        assert result["_naive_tokens"] == 0
