from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser
from codegraph.domain.models import SymbolKind, EdgeKind


class TestTreeSitterParserPython:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_extract_function(self):
        code = 'def hello(name: str) -> str:\n    """Say hello."""\n    return f"Hello {name}"\n'
        symbols, edges, diags = self.parser.parse_file("test.py", code, "python")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "hello"
        assert funcs[0].signature == "def hello(name: str) -> str"

    def test_extract_class_and_methods(self):
        code = (
            "class MyService:\n"
            "    def process(self, data: dict) -> bool:\n"
            "        return True\n"
        )
        symbols, edges, diags = self.parser.parse_file("test.py", code, "python")
        classes = [s for s in symbols if s.kind == SymbolKind.CLASS]
        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        assert len(classes) == 1
        assert len(methods) == 1
        assert methods[0].container_name == "MyService"

    def test_extract_import_edges(self):
        code = "from auth.middleware import verify_token\nimport os\n"
        symbols, edges, diags = self.parser.parse_file("test.py", code, "python")
        import_edges = [e for e in edges if e.kind == EdgeKind.IMPORTS]
        assert len(import_edges) >= 2

    def test_extract_call_edges(self):
        code = "def main():\n    result = verify_token(request)\n"
        symbols, edges, diags = self.parser.parse_file("test.py", code, "python")
        call_edges = [e for e in edges if e.kind == EdgeKind.CALLS]
        assert len(call_edges) >= 1
        assert "verify_token" in call_edges[0].ref_text

    def test_extract_inheritance(self):
        code = "class Admin(User):\n    pass\n"
        symbols, edges, diags = self.parser.parse_file("test.py", code, "python")
        inherit_edges = [e for e in edges if e.kind == EdgeKind.INHERITS]
        assert len(inherit_edges) == 1

    def test_parse_error_reported(self):
        code = "def broken(:\n    pass\n"
        symbols, edges, diags = self.parser.parse_file("test.py", code, "python")
        assert len(diags) > 0

    def test_docstring_extraction(self):
        code = 'def hello():\n    """This is a docstring."""\n    pass\n'
        symbols, _, _ = self.parser.parse_file("test.py", code, "python")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert funcs[0].docstring == "This is a docstring."

    def test_unsupported_language_returns_empty(self):
        symbols, edges, diags = self.parser.parse_file("test.unknown", "some code", None)
        assert symbols == []

    def test_decorator_extraction(self):
        code = "@staticmethod\ndef helper():\n    pass\n"
        symbols, _, _ = self.parser.parse_file("test.py", code, "python")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        # Decorators should be captured - the function is still extracted
        assert funcs[0].name == "helper"
