"""Tests for graph query tool use cases."""

import pytest
from unittest.mock import MagicMock

from codegraph.domain.models import Symbol, Edge, SymbolKind, EdgeKind
from codegraph.application.tools.get_symbols import GetSymbolsUseCase
from codegraph.application.tools.get_symbol import GetSymbolUseCase
from codegraph.application.tools.get_imports import GetImportsUseCase
from codegraph.application.tools.get_dependents import GetDependentsUseCase
from codegraph.application.tools.get_call_graph import GetCallGraphUseCase
from codegraph.application.tools.get_hierarchy import GetHierarchyUseCase
from codegraph.application.tools.find_references import FindReferencesUseCase
from codegraph.application.tools.resolve_symbol import ResolveSymbolUseCase


@pytest.fixture
def sample_symbol():
    return Symbol(
        name="hello",
        kind=SymbolKind.FUNCTION,
        file_path="test.py",
        start_line=1,
        end_line=5,
        signature="def hello()",
        language="python",
        module_path="test",
    )


@pytest.fixture
def sample_edge():
    return Edge(
        source_symbol_id="a.py:foo:function:1",
        target_symbol_id="b.py:bar:function:10",
        kind=EdgeKind.CALLS,
        file_path="a.py",
        start_line=5,
        end_line=5,
        column=8,
        ref_text="bar(x)",
        index_generation=1,
    )


class TestGetSymbolsUseCase:
    def test_returns_symbols(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], None)
        use_case = GetSymbolsUseCase(store)
        result = use_case.execute(file_path="test.py")
        assert result["count"] == 1
        assert result["symbols"][0]["name"] == "hello"
        store.query_symbols.assert_called_once_with(
            file_path="test.py", kind=None, max_results=50, cursor=None,
        )

    def test_name_pattern_filter(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], None)
        use_case = GetSymbolsUseCase(store)
        result = use_case.execute(name_pattern="xyz")
        assert result["count"] == 0

    def test_name_pattern_matches(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], None)
        use_case = GetSymbolsUseCase(store)
        result = use_case.execute(name_pattern="hel")
        assert result["count"] == 1

    def test_pagination_cursor(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], "next_page")
        use_case = GetSymbolsUseCase(store)
        result = use_case.execute()
        assert result["next_cursor"] == "next_page"

    def test_empty_results(self):
        store = MagicMock()
        store.query_symbols.return_value = ([], None)
        use_case = GetSymbolsUseCase(store)
        result = use_case.execute()
        assert result["count"] == 0
        assert result["symbols"] == []

    def test_serialize_all_fields(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], None)
        use_case = GetSymbolsUseCase(store)
        result = use_case.execute()
        s = result["symbols"][0]
        assert s["symbol_id"] == sample_symbol.symbol_id
        assert s["kind"] == "function"
        assert s["file_path"] == "test.py"
        assert s["start_line"] == 1
        assert s["end_line"] == 5
        assert s["signature"] == "def hello()"
        assert s["module_path"] == "test"


class TestGetSymbolUseCase:
    def test_by_id(self, sample_symbol):
        store = MagicMock()
        store.get_symbol.return_value = sample_symbol
        use_case = GetSymbolUseCase(store)
        result = use_case.execute(symbol_id=sample_symbol.symbol_id)
        assert result["symbol"]["name"] == "hello"
        store.get_symbol.assert_called_once_with(sample_symbol.symbol_id)

    def test_by_key(self, sample_symbol):
        store = MagicMock()
        store.get_symbol_by_key.return_value = sample_symbol
        use_case = GetSymbolUseCase(store)
        result = use_case.execute(symbol_key="test.hello:function")
        assert result["symbol"]["name"] == "hello"
        store.get_symbol_by_key.assert_called_once_with("test.hello:function")

    def test_not_found(self):
        store = MagicMock()
        store.get_symbol.return_value = None
        use_case = GetSymbolUseCase(store)
        result = use_case.execute(symbol_id="nonexistent")
        assert result["symbol"] is None

    def test_no_args_returns_error(self):
        store = MagicMock()
        use_case = GetSymbolUseCase(store)
        result = use_case.execute()
        assert "error" in result

    def test_serialize_includes_docstring(self):
        sym = Symbol(
            name="greet", kind=SymbolKind.FUNCTION, file_path="a.py",
            start_line=1, end_line=3, signature="def greet(name)",
            language="python", docstring="Say hello.",
        )
        store = MagicMock()
        store.get_symbol.return_value = sym
        use_case = GetSymbolUseCase(store)
        result = use_case.execute(symbol_id=sym.symbol_id)
        assert result["symbol"]["docstring"] == "Say hello."


class TestGetImportsUseCase:
    def test_returns_imports(self):
        edge = Edge(
            source_symbol_id="a.py:main:function:1",
            kind=EdgeKind.IMPORTS,
            file_path="a.py",
            start_line=1,
            end_line=1,
            column=0,
            ref_text="import os",
            index_generation=1,
        )
        store = MagicMock()
        store.get_edges.return_value = ([edge], None)
        use_case = GetImportsUseCase(store)
        result = use_case.execute(file_path="a.py")
        assert result["count"] == 1
        assert result["imports"][0]["ref_text"] == "import os"
        store.get_edges.assert_called_once_with(
            source_id=None, file_path="a.py", kind=EdgeKind.IMPORTS,
        )

    def test_by_symbol(self):
        edge = Edge(
            source_symbol_id="a.py:main:function:1",
            kind=EdgeKind.IMPORTS,
            file_path="a.py",
            start_line=2,
            end_line=2,
            column=0,
            ref_text="import sys",
            index_generation=1,
        )
        store = MagicMock()
        store.get_edges.return_value = ([edge], None)
        use_case = GetImportsUseCase(store)
        result = use_case.execute(symbol_id="a.py:main:function:1")
        assert result["count"] == 1
        store.get_edges.assert_called_once_with(
            source_id="a.py:main:function:1", file_path=None, kind=EdgeKind.IMPORTS,
        )

    def test_empty_imports(self):
        store = MagicMock()
        store.get_edges.return_value = ([], None)
        use_case = GetImportsUseCase(store)
        result = use_case.execute(file_path="empty.py")
        assert result["count"] == 0
        assert result["imports"] == []


class TestGetDependentsUseCase:
    def test_returns_dependents(self, sample_edge):
        store = MagicMock()
        store.get_edges.return_value = ([sample_edge], None)
        use_case = GetDependentsUseCase(store)
        result = use_case.execute(symbol_id="b.py:bar:function:10")
        assert result["count"] == 1
        assert result["dependents"][0]["source_symbol_id"] == "a.py:foo:function:1"
        store.get_edges.assert_called_once_with(target_id="b.py:bar:function:10")

    def test_empty_dependents(self):
        store = MagicMock()
        store.get_edges.return_value = ([], None)
        use_case = GetDependentsUseCase(store)
        result = use_case.execute(symbol_id="isolated:sym:function:1")
        assert result["count"] == 0


class TestGetCallGraphUseCase:
    def test_outgoing(self, sample_edge):
        store = MagicMock()
        store.get_edges.return_value = ([sample_edge], None)
        use_case = GetCallGraphUseCase(store)
        result = use_case.execute("a.py:foo:function:1", direction="outgoing")
        assert result["count"] == 1
        assert result["direction"] == "outgoing"
        store.get_edges.assert_called_once_with(
            source_id="a.py:foo:function:1", kind=EdgeKind.CALLS,
        )

    def test_incoming(self, sample_edge):
        store = MagicMock()
        store.get_edges.return_value = ([sample_edge], None)
        use_case = GetCallGraphUseCase(store)
        result = use_case.execute("b.py:bar:function:10", direction="incoming")
        assert result["count"] == 1
        assert result["direction"] == "incoming"
        store.get_edges.assert_called_once_with(
            target_id="b.py:bar:function:10", kind=EdgeKind.CALLS,
        )

    def test_call_serialization(self, sample_edge):
        store = MagicMock()
        store.get_edges.return_value = ([sample_edge], None)
        use_case = GetCallGraphUseCase(store)
        result = use_case.execute("a.py:foo:function:1")
        call = result["calls"][0]
        assert call["source_symbol_id"] == "a.py:foo:function:1"
        assert call["target_symbol_id"] == "b.py:bar:function:10"
        assert call["ref_text"] == "bar(x)"
        assert call["file_path"] == "a.py"
        assert call["line"] == 5


class TestGetHierarchyUseCase:
    def test_ancestors(self):
        edge = Edge(
            source_symbol_id="a.py:Admin:class:1",
            kind=EdgeKind.INHERITS,
            file_path="a.py",
            start_line=1,
            end_line=1,
            column=0,
            ref_text="User",
            index_generation=1,
            target_symbol_id="models.py:User:class:5",
        )
        store = MagicMock()
        store.get_edges.return_value = ([edge], None)
        use_case = GetHierarchyUseCase(store)
        result = use_case.execute("a.py:Admin:class:1", direction="ancestors")
        assert result["count"] == 1
        assert result["direction"] == "ancestors"
        store.get_edges.assert_called_once_with(
            source_id="a.py:Admin:class:1", kind=EdgeKind.INHERITS,
        )

    def test_descendants(self):
        edge = Edge(
            source_symbol_id="a.py:Admin:class:1",
            kind=EdgeKind.INHERITS,
            file_path="a.py",
            start_line=1,
            end_line=1,
            column=0,
            ref_text="User",
            index_generation=1,
            target_symbol_id="models.py:User:class:5",
        )
        store = MagicMock()
        store.get_edges.return_value = ([edge], None)
        use_case = GetHierarchyUseCase(store)
        result = use_case.execute("models.py:User:class:5", direction="descendants")
        assert result["count"] == 1
        assert result["direction"] == "descendants"
        store.get_edges.assert_called_once_with(
            target_id="models.py:User:class:5", kind=EdgeKind.INHERITS,
        )

    def test_hierarchy_serialization(self):
        edge = Edge(
            source_symbol_id="a.py:Admin:class:1",
            kind=EdgeKind.INHERITS,
            file_path="a.py",
            start_line=1,
            end_line=1,
            column=0,
            ref_text="User",
            index_generation=1,
            target_symbol_id="models.py:User:class:5",
        )
        store = MagicMock()
        store.get_edges.return_value = ([edge], None)
        use_case = GetHierarchyUseCase(store)
        result = use_case.execute("a.py:Admin:class:1")
        h = result["hierarchy"][0]
        assert h["source_symbol_id"] == "a.py:Admin:class:1"
        assert h["target_symbol_id"] == "models.py:User:class:5"
        assert h["kind"] == "inherits"


class TestFindReferencesUseCase:
    def test_returns_references(self, sample_edge):
        store = MagicMock()
        store.get_edges.return_value = ([sample_edge], None)
        use_case = FindReferencesUseCase(store)
        result = use_case.execute(symbol_id="b.py:bar:function:10")
        assert result["count"] == 1
        ref = result["references"][0]
        assert ref["source_symbol_id"] == "a.py:foo:function:1"
        assert ref["kind"] == "calls"
        assert ref["ref_text"] == "bar(x)"
        assert ref["start_line"] == 5
        assert ref["column"] == 8

    def test_empty_references(self):
        store = MagicMock()
        store.get_edges.return_value = ([], None)
        use_case = FindReferencesUseCase(store)
        result = use_case.execute(symbol_id="unreferenced:sym:function:1")
        assert result["count"] == 0
        assert result["references"] == []


class TestResolveSymbolUseCase:
    def test_resolves_by_name(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], None)
        use_case = ResolveSymbolUseCase(store)
        result = use_case.execute("hello")
        assert result["count"] == 1
        assert result["candidates"][0]["name"] == "hello"

    def test_no_match(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], None)
        use_case = ResolveSymbolUseCase(store)
        result = use_case.execute("nonexistent")
        assert result["count"] == 0

    def test_file_context_prioritization(self):
        sym_a = Symbol(
            name="process", kind=SymbolKind.FUNCTION, file_path="a.py",
            start_line=1, end_line=5, signature="def process()",
            language="python",
        )
        sym_b = Symbol(
            name="process", kind=SymbolKind.FUNCTION, file_path="b.py",
            start_line=1, end_line=5, signature="def process(data)",
            language="python",
        )
        store = MagicMock()
        store.query_symbols.return_value = ([sym_a, sym_b], None)
        use_case = ResolveSymbolUseCase(store)
        result = use_case.execute("process", file_context="b.py")
        assert result["count"] == 2
        # b.py symbol should come first
        assert result["candidates"][0]["file_path"] == "b.py"
        assert result["candidates"][1]["file_path"] == "a.py"

    def test_kind_filter_passed(self, sample_symbol):
        store = MagicMock()
        store.query_symbols.return_value = ([sample_symbol], None)
        use_case = ResolveSymbolUseCase(store)
        use_case.execute("hello", kind=SymbolKind.FUNCTION)
        store.query_symbols.assert_called_once_with(
            kind=SymbolKind.FUNCTION, max_results=200,
        )
