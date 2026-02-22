import pytest
import json
from codegraph.domain.models import Symbol, Edge, Chunk, SymbolKind, EdgeKind
from codegraph.domain.workspace import (
    WorkspaceState, EmbeddingMetadata, IndexMetadata, FileDiagnostic, ParseStatus,
)
from codegraph.infrastructure.storage.lancedb_store import LanceDBStore


@pytest.fixture
def store(tmp_path):
    s = LanceDBStore(str(tmp_path / "test.lance"))
    yield s
    s.close()


@pytest.fixture
def sample_symbol():
    return Symbol(
        name="verify_token",
        kind=SymbolKind.FUNCTION,
        file_path="src/auth.py",
        start_line=42,
        end_line=68,
        signature="def verify_token(request: Request) -> bool",
        language="python",
        module_path="src.auth",
        index_generation=1,
    )


class TestLanceDBStoreSymbols:
    def test_upsert_and_get_symbol(self, store, sample_symbol):
        store.upsert_symbols([sample_symbol])
        result = store.get_symbol(sample_symbol.symbol_id)
        assert result is not None
        assert result.name == "verify_token"

    def test_get_symbol_by_key(self, store, sample_symbol):
        store.upsert_symbols([sample_symbol])
        result = store.get_symbol_by_key(sample_symbol.symbol_key)
        assert result is not None
        assert result.symbol_id == sample_symbol.symbol_id

    def test_query_symbols_by_file(self, store, sample_symbol):
        store.upsert_symbols([sample_symbol])
        results, cursor = store.query_symbols(file_path="src/auth.py")
        assert len(results) == 1

    def test_query_symbols_by_kind(self, store, sample_symbol):
        store.upsert_symbols([sample_symbol])
        results, _ = store.query_symbols(kind=SymbolKind.FUNCTION)
        assert len(results) == 1

    def test_delete_symbols_by_file(self, store, sample_symbol):
        store.upsert_symbols([sample_symbol])
        store.delete_symbols_by_file("src/auth.py")
        result = store.get_symbol(sample_symbol.symbol_id)
        assert result is None

    def test_query_pagination(self, store):
        symbols = [
            Symbol(
                name=f"func_{i}", kind=SymbolKind.FUNCTION,
                file_path="a.py", start_line=i, end_line=i + 5,
                signature=f"def func_{i}()", language="python",
                index_generation=1,
            )
            for i in range(10)
        ]
        store.upsert_symbols(symbols)
        results, cursor = store.query_symbols(max_results=3)
        assert len(results) == 3
        assert cursor is not None
        results2, cursor2 = store.query_symbols(max_results=3, cursor=cursor)
        assert len(results2) == 3


class TestLanceDBStoreEdges:
    def test_upsert_and_query_edges(self, store):
        edge = Edge(
            source_symbol_id="a.py:foo:function:1",
            target_symbol_id="b.py:bar:function:10",
            kind=EdgeKind.CALLS,
            file_path="a.py",
            start_line=5, end_line=5, column=8,
            ref_text="bar(x)",
            index_generation=1,
        )
        store.upsert_edges([edge])
        results, _ = store.get_edges(source_id="a.py:foo:function:1")
        assert len(results) == 1
        assert results[0].edge_id == edge.edge_id

    def test_delete_edges_by_file(self, store):
        edge = Edge(
            source_symbol_id="a.py:foo:function:1",
            kind=EdgeKind.IMPORTS, file_path="a.py",
            start_line=1, end_line=1, column=0,
            ref_text="import bar", index_generation=1,
        )
        store.upsert_edges([edge])
        store.delete_edges_by_file("a.py")
        results, _ = store.get_edges(file_path="a.py")
        assert len(results) == 0


class TestLanceDBStoreChunks:
    def test_upsert_and_get_chunks(self, store):
        chunk = Chunk(
            file_path="a.py", start_line=1, end_line=10,
            content="def foo():\n    pass\n",
            symbol_ids=[], is_symbol_chunk=False,
            index_generation=1,
        )
        store.upsert_chunks([chunk])
        results = store.get_chunks(file_path="a.py")
        assert len(results) == 1

    def test_get_chunks_needs_embedding(self, store):
        chunk = Chunk(
            file_path="a.py", start_line=1, end_line=10,
            content="code", symbol_ids=[], is_symbol_chunk=False,
            has_vector=False, index_generation=1,
        )
        store.upsert_chunks([chunk])
        results = store.get_chunks(has_vector=False)
        assert len(results) == 1


class TestLanceDBStoreMetadata:
    def test_set_and_get_metadata(self, store):
        meta = IndexMetadata(
            workspace_state=WorkspaceState(
                head_commit="abc1234", index_base="abc1234", worktree_dirty=False,
            ),
            embedding=EmbeddingMetadata(
                provider_id="local", model="nomic", model_revision=None,
                runtime="onnx", device="cpu", actual_dimension=768,
                requested_dimension=None, config_hash="abc", input_version=1,
                normalize="l2",
            ),
            generation=1,
        )
        store.set_metadata(meta)
        loaded = store.get_metadata()
        assert loaded is not None
        assert loaded.generation == 1
        assert loaded.workspace_state.head_commit == "abc1234"
