import pytest
from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser
from codegraph.domain.models import SymbolKind, EdgeKind


class TestTypeScriptExtractor:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_extract_function_declaration(self):
        code = "function greet(name: string): string {\n  return `Hello ${name}`;\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "greet"

    def test_extract_arrow_function(self):
        code = "const add = (a: number, b: number): number => a + b;\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "add"

    def test_extract_class(self):
        code = "class UserService {\n  getUser(id: string): User {\n    return {} as User;\n  }\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        classes = [s for s in symbols if s.kind == SymbolKind.CLASS]
        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        assert len(classes) == 1
        assert classes[0].name == "UserService"
        assert len(methods) == 1
        assert methods[0].container_name == "UserService"

    def test_extract_interface(self):
        code = "interface Config {\n  host: string;\n  port: number;\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        interfaces = [s for s in symbols if s.kind == SymbolKind.INTERFACE]
        assert len(interfaces) == 1
        assert interfaces[0].name == "Config"

    def test_extract_type_alias(self):
        code = "type ID = string | number;\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        types = [s for s in symbols if s.kind == SymbolKind.TYPE_ALIAS]
        assert len(types) == 1
        assert types[0].name == "ID"

    def test_extract_enum(self):
        code = "enum Status {\n  Active,\n  Inactive,\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        enums = [s for s in symbols if s.kind == SymbolKind.ENUM]
        assert len(enums) == 1

    def test_extract_imports(self):
        code = "import { Router } from 'express';\nimport * as path from 'path';\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        import_edges = [e for e in edges if e.kind == EdgeKind.IMPORTS]
        assert len(import_edges) >= 2

    def test_extract_inheritance(self):
        code = "class Admin extends User implements Serializable {\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        inherits = [e for e in edges if e.kind == EdgeKind.INHERITS]
        implements = [e for e in edges if e.kind == EdgeKind.IMPLEMENTS]
        assert len(inherits) == 1
        assert len(implements) == 1

    def test_extract_calls(self):
        code = "function main() {\n  const result = fetchData(url);\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        calls = [e for e in edges if e.kind == EdgeKind.CALLS]
        assert len(calls) >= 1

    def test_extract_generator_function(self):
        code = "function* gen() {\n  yield 1;\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "gen"

    def test_extract_exported_function(self):
        code = "export function exportedFunc() {}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "exportedFunc"

    def test_extract_exported_class(self):
        code = "export class MyService {\n  run(): void {}\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        classes = [s for s in symbols if s.kind == SymbolKind.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "MyService"

    def test_extract_default_import(self):
        code = "import defaultExport from 'module';\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        import_edges = [e for e in edges if e.kind == EdgeKind.IMPORTS]
        assert len(import_edges) == 1
        assert "defaultExport" in import_edges[0].ref_text

    def test_parse_error_reported(self):
        code = "function broken( {\n  return;\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        assert len(diags) > 0

    def test_jsdoc_extraction(self):
        code = "/**\n * Greet a user.\n */\nfunction greet(name: string): string {\n  return name;\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].docstring is not None
        assert "Greet a user" in funcs[0].docstring

    def test_tsx_uses_typescript_extractor(self):
        code = "function App(): JSX.Element {\n  return <div />;\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.tsx", code, "tsx")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "App"

    def test_function_signature_includes_params_and_return_type(self):
        code = "function greet(name: string): string {\n  return name;\n}\n"
        symbols, _, _ = self.parser.parse_file("test.ts", code, "typescript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert "name: string" in funcs[0].signature
        assert "string" in funcs[0].signature

    def test_class_with_multiple_methods(self):
        code = "class Foo {\n  bar(): void {}\n  baz(x: number): number { return x; }\n}\n"
        symbols, _, _ = self.parser.parse_file("test.ts", code, "typescript")
        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) == 2
        names = {m.name for m in methods}
        assert "bar" in names
        assert "baz" in names

    def test_interface_with_extends(self):
        code = "interface Config extends BaseConfig {\n  host: string;\n}\n"
        symbols, _, _ = self.parser.parse_file("test.ts", code, "typescript")
        interfaces = [s for s in symbols if s.kind == SymbolKind.INTERFACE]
        assert len(interfaces) == 1
        assert "extends" in interfaces[0].signature

    def test_multiple_implements(self):
        code = "class Admin extends User implements Serializable, Printable {\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.ts", code, "typescript")
        implements = [e for e in edges if e.kind == EdgeKind.IMPLEMENTS]
        assert len(implements) == 2


class TestJavaScriptExtractor:
    def setup_method(self):
        self.parser = TreeSitterParser()

    def test_extract_function(self):
        code = "function hello(name) {\n  return 'Hello ' + name;\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.js", code, "javascript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1

    def test_extract_arrow_function(self):
        code = "const add = (a, b) => a + b;\n"
        symbols, edges, diags = self.parser.parse_file("test.js", code, "javascript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1

    def test_extract_class(self):
        code = "class Animal {\n  constructor(name) {\n    this.name = name;\n  }\n  speak() {\n    return this.name;\n  }\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.js", code, "javascript")
        classes = [s for s in symbols if s.kind == SymbolKind.CLASS]
        assert len(classes) == 1

    def test_extract_require_imports(self):
        code = "const express = require('express');\n"
        symbols, edges, diags = self.parser.parse_file("test.js", code, "javascript")
        import_edges = [e for e in edges if e.kind == EdgeKind.IMPORTS]
        assert len(import_edges) >= 1

    def test_extract_es6_imports(self):
        code = "import { Router } from 'express';\n"
        symbols, edges, diags = self.parser.parse_file("test.js", code, "javascript")
        import_edges = [e for e in edges if e.kind == EdgeKind.IMPORTS]
        assert len(import_edges) >= 1

    def test_extract_class_with_extends(self):
        code = "class Dog extends Animal {\n  bark() { return 'Woof'; }\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.js", code, "javascript")
        inherits = [e for e in edges if e.kind == EdgeKind.INHERITS]
        assert len(inherits) == 1

    def test_extract_calls(self):
        code = "function main() {\n  console.log('hello');\n}\n"
        symbols, edges, diags = self.parser.parse_file("test.js", code, "javascript")
        calls = [e for e in edges if e.kind == EdgeKind.CALLS]
        assert len(calls) >= 1

    def test_jsx_uses_javascript_extractor(self):
        code = "function App() {\n  return <div />;\n}\n"
        # JSX parsed as javascript
        symbols, edges, diags = self.parser.parse_file("test.jsx", code, "jsx")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1

    def test_generator_function(self):
        code = "function* gen() {\n  yield 1;\n}\n"
        symbols, _, _ = self.parser.parse_file("test.js", code, "javascript")
        funcs = [s for s in symbols if s.kind == SymbolKind.FUNCTION]
        assert len(funcs) == 1
        assert funcs[0].name == "gen"

    def test_class_methods_have_container(self):
        code = "class Foo {\n  bar() {}\n}\n"
        symbols, _, _ = self.parser.parse_file("test.js", code, "javascript")
        methods = [s for s in symbols if s.kind == SymbolKind.METHOD]
        assert len(methods) == 1
        assert methods[0].container_name == "Foo"
