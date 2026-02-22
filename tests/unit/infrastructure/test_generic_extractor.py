import pytest
from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser
from codegraph.domain.models import SymbolKind, EdgeKind


class TestGenericExtractorGo:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_extract_go_function(self):
        code = (
            "package main\n"
            "\n"
            'func greet(name string) string {\n'
            '\treturn "Hello " + name\n'
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("main.go", code, "go")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) >= 1
        assert funcs[0].name == "greet"

    def test_extract_go_struct(self):
        code = (
            "package main\n"
            "\n"
            "type User struct {\n"
            "\tName string\n"
            "\tAge  int\n"
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("main.go", code, "go")
        # Go structs are wrapped in type_declaration; the generic extractor
        # captures it as a TYPE symbol with name "User".
        assert len(symbols) >= 1

    def test_extract_go_method(self):
        code = (
            "package main\n"
            "\n"
            "func (u *User) Greet() string {\n"
            "\treturn u.Name\n"
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("main.go", code, "go")
        assert len(symbols) >= 1


class TestGenericExtractorRust:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_extract_rust_function(self):
        code = (
            'fn greet(name: &str) -> String {\n'
            '    format!("Hello {}", name)\n'
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("main.rs", code, "rust")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) >= 1
        assert funcs[0].name == "greet"

    def test_extract_rust_struct(self):
        code = (
            "struct User {\n"
            "    name: String,\n"
            "    age: u32,\n"
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("main.rs", code, "rust")
        assert len(symbols) >= 1

    def test_extract_rust_impl(self):
        code = (
            "impl User {\n"
            "    fn new(name: String) -> Self {\n"
            "        User { name, age: 0 }\n"
            "    }\n"
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("main.rs", code, "rust")
        funcs = [s for s in symbols if s.kind in (SymbolKind.FUNCTION, SymbolKind.METHOD)]
        assert len(funcs) >= 1


class TestGenericExtractorJava:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_extract_java_class(self):
        code = (
            "public class UserService {\n"
            "    public User getUser(String id) {\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("UserService.java", code, "java")
        classes = [s for s in symbols if s.kind == SymbolKind.CLASS]
        assert len(classes) >= 1
        assert classes[0].name == "UserService"

    def test_extract_java_method(self):
        code = (
            "public class Foo {\n"
            '    public void bar() {\n'
            '        System.out.println("hi");\n'
            "    }\n"
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("Foo.java", code, "java")
        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) >= 1


class TestGenericExtractorEdges:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_extract_java_call_edges(self):
        code = (
            "public class Foo {\n"
            '    public void bar() {\n'
            '        System.out.println("hi");\n'
            "    }\n"
            "}\n"
        )
        symbols, edges, diags = self.parser.parse_file("Foo.java", code, "java")
        call_edges = [e for e in edges if e.kind == EdgeKind.CALLS]
        assert len(call_edges) >= 1

    def test_extract_rust_use_edge(self):
        code = (
            "use std::collections::HashMap;\n"
            "\n"
            "fn main() {}\n"
        )
        symbols, edges, diags = self.parser.parse_file("main.rs", code, "rust")
        import_edges = [e for e in edges if e.kind == EdgeKind.IMPORTS]
        assert len(import_edges) >= 1


class TestGenericExtractorDiagnostics:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_rust_parse_error(self):
        code = "fn broken( {\n}\n"
        symbols, edges, diags = self.parser.parse_file("main.rs", code, "rust")
        assert len(diags) > 0


class TestGenericExtractorDoesNotBreakExisting:
    """Verify the generic extractor does not affect Python or truly unknown files."""

    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_python_still_uses_python_extractor(self):
        code = "def hello():\n    pass\n"
        symbols, edges, diags = self.parser.parse_file("test.py", code, "python")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "hello"

    def test_unsupported_language_still_returns_empty(self):
        """Files with no grammar (unknown extension) still return empty."""
        symbols, edges, diags = self.parser.parse_file("test.unknown", "some code", None)
        assert symbols == []
        assert edges == []
        assert diags == []
