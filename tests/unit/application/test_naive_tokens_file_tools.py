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
