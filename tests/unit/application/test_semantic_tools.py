"""Tests for semantic search and overview tool use cases."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from codegraph.domain.models import Symbol, SymbolKind, EdgeKind, Edge, Chunk
from codegraph.domain.workspace import (
    IndexMetadata, WorkspaceState, EmbeddingMetadata,
)
from codegraph.application.tools.semantic_search import SemanticSearchUseCase
from codegraph.application.tools.get_file_summary import GetFileSummaryUseCase
from codegraph.application.tools.get_repo_overview import GetRepoOverviewUseCase


class TestSemanticSearchUseCase:
    @pytest.mark.asyncio
    async def test_no_provider_returns_error(self):
        store = MagicMock()
        use_case = SemanticSearchUseCase(store, embedding_provider=None)
        result = await use_case.execute("search query")
        assert "error" in result
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_with_mocked_provider(self):
        store = MagicMock()
        store.vector_search.return_value = []
        provider = MagicMock()
        provider.embed_single = AsyncMock(return_value=[0.1] * 10)
        use_case = SemanticSearchUseCase(store, provider)
        result = await use_case.execute("query")
        assert result["count"] == 0
        assert result["query"] == "query"
        provider.embed_single.assert_awaited_once_with("query")

    @pytest.mark.asyncio
    async def test_returns_chunk_results(self):
        chunk = Chunk(
            file_path="example.py",
            start_line=1,
            end_line=10,
            content="def hello():\n    pass",
            symbol_ids=["example.py:hello:function:1"],
            is_symbol_chunk=True,
        )
        store = MagicMock()
        store.vector_search.return_value = [chunk]
        provider = MagicMock()
        provider.embed_single = AsyncMock(return_value=[0.1] * 10)
        use_case = SemanticSearchUseCase(store, provider)
        result = await use_case.execute("hello function")
        assert result["count"] == 1
        r = result["results"][0]
        assert r["file_path"] == "example.py"
        assert r["start_line"] == 1
        assert r["symbol_ids"] == ["example.py:hello:function:1"]
        assert "hello" in r["content_preview"]

    @pytest.mark.asyncio
    async def test_content_preview_truncation(self):
        long_content = "x" * 300
        chunk = Chunk(
            file_path="big.py",
            start_line=1,
            end_line=50,
            content=long_content,
            symbol_ids=[],
            is_symbol_chunk=False,
        )
        store = MagicMock()
        store.vector_search.return_value = [chunk]
        provider = MagicMock()
        provider.embed_single = AsyncMock(return_value=[0.1] * 10)
        use_case = SemanticSearchUseCase(store, provider)
        result = await use_case.execute("query")
        preview = result["results"][0]["content_preview"]
        assert preview.endswith("...")
        assert len(preview) == 203  # 200 chars + "..."

    @pytest.mark.asyncio
    async def test_file_filter_passed(self):
        store = MagicMock()
        store.vector_search.return_value = []
        provider = MagicMock()
        provider.embed_single = AsyncMock(return_value=[0.1] * 10)
        use_case = SemanticSearchUseCase(store, provider)
        await use_case.execute("query", file_filter="src/")
        store.vector_search.assert_called_once_with(
            query_vector=[0.1] * 10, top_k=10, file_filter="src/",
        )


class TestGetFileSummaryUseCase:
    def test_returns_summary(self):
        sym = Symbol(
            name="hello",
            kind=SymbolKind.FUNCTION,
            file_path="test.py",
            start_line=1,
            end_line=2,
            signature="def hello()",
            language="python",
        )
        store = MagicMock()
        store.query_symbols.return_value = ([sym], None)
        store.get_edges.return_value = ([], None)
        use_case = GetFileSummaryUseCase(store)
        result = use_case.execute("test.py")
        assert result["symbol_count"] == 1
        assert result["file_path"] == "test.py"
        assert result["edge_count"] == 0
        assert result["import_count"] == 0

    def test_counts_imports(self):
        sym = Symbol(
            name="main", kind=SymbolKind.FUNCTION, file_path="app.py",
            start_line=5, end_line=10, signature="def main()",
            language="python",
        )
        import_edge = Edge(
            source_symbol_id="app.py:main:function:5",
            kind=EdgeKind.IMPORTS, file_path="app.py",
            start_line=1, end_line=1, column=0,
            ref_text="import os", index_generation=1,
        )
        call_edge = Edge(
            source_symbol_id="app.py:main:function:5",
            kind=EdgeKind.CALLS, file_path="app.py",
            start_line=7, end_line=7, column=4,
            ref_text="print()", index_generation=1,
        )
        store = MagicMock()
        store.query_symbols.return_value = ([sym], None)
        store.get_edges.return_value = ([import_edge, call_edge], None)
        use_case = GetFileSummaryUseCase(store)
        result = use_case.execute("app.py")
        assert result["symbol_count"] == 1
        assert result["edge_count"] == 2
        assert result["import_count"] == 1

    def test_symbol_serialization(self):
        sym = Symbol(
            name="MyClass", kind=SymbolKind.CLASS, file_path="models.py",
            start_line=10, end_line=50, signature="class MyClass(Base)",
            language="python",
        )
        store = MagicMock()
        store.query_symbols.return_value = ([sym], None)
        store.get_edges.return_value = ([], None)
        use_case = GetFileSummaryUseCase(store)
        result = use_case.execute("models.py")
        s = result["symbols"][0]
        assert s["name"] == "MyClass"
        assert s["kind"] == "class"
        assert s["start_line"] == 10
        assert s["end_line"] == 50
        assert s["signature"] == "class MyClass(Base)"

    def test_empty_file(self):
        store = MagicMock()
        store.query_symbols.return_value = ([], None)
        store.get_edges.return_value = ([], None)
        use_case = GetFileSummaryUseCase(store)
        result = use_case.execute("empty.py")
        assert result["symbol_count"] == 0
        assert result["symbols"] == []


class TestGetRepoOverviewUseCase:
    def test_with_metadata(self):
        store = MagicMock()
        store.get_metadata.return_value = IndexMetadata(
            workspace_state=WorkspaceState(
                head_commit="abc123",
                index_base="abc123",
                worktree_dirty=False,
            ),
            embedding=EmbeddingMetadata(
                provider_id="onnx-local",
                model="all-MiniLM-L6-v2",
                model_revision=None,
                runtime="onnxruntime",
                device="cpu",
                actual_dimension=384,
                requested_dimension=None,
                config_hash="deadbeef",
                input_version=1,
                normalize="l2",
            ),
            generation=3,
            file_manifest={
                "a.py": MagicMock(),
                "b.py": MagicMock(),
            },
        )
        git = MagicMock()
        git.is_dirty.return_value = False
        git.get_head_commit.return_value = "abc123"
        use_case = GetRepoOverviewUseCase(store, git)
        result = use_case.execute()
        assert result["indexed"] is True
        assert result["generation"] == 3
        assert result["head_commit"] == "abc123"
        assert result["file_count"] == 2
        assert result["embedding_provider"] == "onnx-local"
        assert result["embedding_model"] == "all-MiniLM-L6-v2"
        assert result["is_dirty"] is False
        assert result["current_head"] == "abc123"

    def test_no_index(self):
        store = MagicMock()
        store.get_metadata.return_value = None
        use_case = GetRepoOverviewUseCase(store)
        result = use_case.execute()
        assert result["indexed"] is False
        assert "generation" not in result

    def test_no_git_client(self):
        store = MagicMock()
        store.get_metadata.return_value = None
        use_case = GetRepoOverviewUseCase(store, git_client=None)
        result = use_case.execute()
        assert "is_dirty" not in result
        assert "current_head" not in result

    def test_stale_index(self):
        store = MagicMock()
        store.get_metadata.return_value = IndexMetadata(
            workspace_state=WorkspaceState(
                head_commit="old_commit",
                index_base="old_commit",
                worktree_dirty=True,
            ),
            embedding=EmbeddingMetadata(
                provider_id="onnx-local",
                model="all-MiniLM-L6-v2",
                model_revision=None,
                runtime="onnxruntime",
                device="cpu",
                actual_dimension=384,
                requested_dimension=None,
                config_hash="deadbeef",
                input_version=1,
                normalize="l2",
            ),
            generation=1,
            file_manifest={"a.py": MagicMock()},
        )
        git = MagicMock()
        git.is_dirty.return_value = True
        git.get_head_commit.return_value = "new_commit"
        use_case = GetRepoOverviewUseCase(store, git)
        result = use_case.execute()
        assert result["indexed"] is True
        assert result["head_commit"] == "old_commit"
        assert result["current_head"] == "new_commit"
        assert result["is_dirty"] is True
