# tests/unit/domain/test_models.py
import pytest
from codegraph.domain.models import Symbol, Edge, Chunk, SymbolKind, EdgeKind, ReferenceKind


class TestSymbol:
    def test_symbol_id_format(self):
        s = Symbol(
            name="verify_token",
            kind=SymbolKind.FUNCTION,
            file_path="src/auth/middleware.py",
            start_line=42,
            end_line=68,
            signature="def verify_token(request: Request) -> bool",
            language="python",
        )
        assert s.symbol_id == "src/auth/middleware.py:verify_token:function:42"

    def test_symbol_key_qualified_name(self):
        s = Symbol(
            name="verify_token",
            kind=SymbolKind.FUNCTION,
            file_path="src/auth/middleware.py",
            start_line=42,
            end_line=68,
            signature="def verify_token(request: Request) -> bool",
            language="python",
            module_path="src.auth.middleware",
        )
        assert s.symbol_key == "src.auth.middleware.verify_token:function"

    def test_symbol_key_fallback_uses_module_format(self):
        """When module_path is empty, file_path is converted to module format."""
        s = Symbol(
            name="verify_token",
            kind=SymbolKind.FUNCTION,
            file_path="src/auth/middleware.py",
            start_line=42,
            end_line=68,
            signature="def verify_token(request: Request) -> bool",
            language="python",
        )
        assert s.symbol_key == "src.auth.middleware.verify_token:function"

    def test_symbol_key_exact_includes_signature_hash(self):
        s = Symbol(
            name="verify_token",
            kind=SymbolKind.FUNCTION,
            file_path="src/auth/middleware.py",
            start_line=42,
            end_line=68,
            signature="def verify_token(request: Request) -> bool",
            language="python",
            module_path="src.auth.middleware",
        )
        assert s.symbol_key_exact.startswith("src.auth.middleware.verify_token:function:")
        assert len(s.symbol_key_exact.split(":")[-1]) == 8

    def test_symbol_key_exact_stable_across_whitespace(self):
        s1 = Symbol(
            name="f", kind=SymbolKind.FUNCTION, file_path="a.py",
            start_line=1, end_line=5,
            signature="def f(  x: int,  y: str  ) -> bool",
            language="python",
        )
        s2 = Symbol(
            name="f", kind=SymbolKind.FUNCTION, file_path="a.py",
            start_line=1, end_line=5,
            signature="def f(x: int, y: str) -> bool",
            language="python",
        )
        assert s1.symbol_key_exact == s2.symbol_key_exact

    def test_symbol_key_exact_differs_on_param_order(self):
        s1 = Symbol(
            name="f", kind=SymbolKind.FUNCTION, file_path="a.py",
            start_line=1, end_line=5,
            signature="def f(x: int, y: str) -> bool",
            language="python",
        )
        s2 = Symbol(
            name="f", kind=SymbolKind.FUNCTION, file_path="a.py",
            start_line=1, end_line=5,
            signature="def f(y: str, x: int) -> bool",
            language="python",
        )
        assert s1.symbol_key_exact != s2.symbol_key_exact

    def test_nested_symbol_key_includes_container(self):
        s = Symbol(
            name="verify",
            kind=SymbolKind.METHOD,
            file_path="src/auth.py",
            start_line=10,
            end_line=20,
            signature="def verify(self, token: str) -> bool",
            language="python",
            module_path="src.auth",
            container_symbol_id="src/auth.py:AuthService:class:5",
            container_name="AuthService",
        )
        assert s.symbol_key == "src.auth.AuthService.verify:method"


class TestEdge:
    def test_edge_id_stable(self):
        e = Edge(
            source_symbol_id="a.py:foo:function:1",
            target_symbol_id="b.py:bar:function:10",
            kind=EdgeKind.CALLS,
            file_path="a.py",
            start_line=5,
            end_line=5,
            column=8,
            ref_text="bar(x)",
        )
        e2 = Edge(
            source_symbol_id="a.py:foo:function:1",
            target_symbol_id="b.py:bar:function:10",
            kind=EdgeKind.CALLS,
            file_path="a.py",
            start_line=5,
            end_line=5,
            column=8,
            ref_text="bar(x)",
        )
        assert e.edge_id == e2.edge_id

    def test_edge_id_excludes_target(self):
        """edge_id must not include target_symbol_id (target is mutable)."""
        e1 = Edge(
            source_symbol_id="a.py:foo:function:1",
            target_symbol_id=None,
            kind=EdgeKind.CALLS,
            file_path="a.py",
            start_line=5, end_line=5, column=8,
            ref_text="bar(x)",
        )
        e2 = Edge(
            source_symbol_id="a.py:foo:function:1",
            target_symbol_id="b.py:bar:function:10",
            kind=EdgeKind.CALLS,
            file_path="a.py",
            start_line=5, end_line=5, column=8,
            ref_text="bar(x)",
        )
        assert e1.edge_id == e2.edge_id


class TestChunk:
    def test_symbol_chunk_id_uses_symbol_key_exact(self):
        c = Chunk(
            file_path="src/auth.py",
            start_line=42,
            end_line=68,
            content="def verify_token(request):\n    pass",
            symbol_ids=["src/auth.py:verify_token:function:42"],
            symbol_key_exact="src.auth.verify_token:function:a3f8b2c1",
            is_symbol_chunk=True,
        )
        assert c.chunk_id == "src.auth.verify_token:function:a3f8b2c1"

    def test_window_chunk_id_uses_path_line_hash(self):
        c = Chunk(
            file_path="src/config.py",
            start_line=1,
            end_line=50,
            content="# config\nFOO = 1\nBAR = 2\n",
            symbol_ids=[],
            is_symbol_chunk=False,
        )
        assert c.chunk_id.startswith("src/config.py:window:1:")
        assert len(c.chunk_id.split(":")[-1]) == 8

    def test_content_hash_stable(self):
        c1 = Chunk(
            file_path="a.py", start_line=1, end_line=10,
            content="def foo():\n    pass\n",
            symbol_ids=[], is_symbol_chunk=False,
        )
        c2 = Chunk(
            file_path="a.py", start_line=1, end_line=10,
            content="def foo():\n    pass\n",
            symbol_ids=[], is_symbol_chunk=False,
        )
        assert c1.content_hash == c2.content_hash
        assert c1.content_hash8 == c2.content_hash8

    def test_content_lines_and_length(self):
        c = Chunk(
            file_path="a.py", start_line=1, end_line=3,
            content="line1\nline2\nline3\n",
            symbol_ids=[], is_symbol_chunk=False,
        )
        assert c.content_lines == 3
        assert c.content_length_chars == len("line1\nline2\nline3\n")
