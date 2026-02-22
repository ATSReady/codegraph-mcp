"""Python-specific tree-sitter extractor."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import Edge, EdgeKind, Symbol, SymbolKind
from codegraph.domain.workspace import FileDiagnostic, ParseStatus
from codegraph.infrastructure.parsers.extractors.base import LanguageExtractor


class PythonExtractor(LanguageExtractor):
    """Extract symbols, edges, and diagnostics from Python source using tree-sitter."""

    LANGUAGE = "python"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_symbols(self, tree: object, source_code: str, file_path: str) -> list[Symbol]:
        symbols: list[Symbol] = []
        root = tree.root_node  # type: ignore[attr-defined]
        self._walk_for_symbols(root, source_code, file_path, symbols, class_stack=[])
        return symbols

    def extract_edges(
        self,
        tree: object,
        source_code: str,
        file_path: str,
        symbols: list[Symbol],
    ) -> list[Edge]:
        edges: list[Edge] = []
        root = tree.root_node  # type: ignore[attr-defined]
        self._walk_for_edges(root, source_code, file_path, symbols, edges, scope_stack=[])
        return edges

    def extract_diagnostics(
        self, tree: object, source_code: str, file_path: str,
    ) -> list[FileDiagnostic]:
        root = tree.root_node  # type: ignore[attr-defined]
        error_spans = self._collect_errors(root)
        if not error_spans:
            return []
        return [
            FileDiagnostic(
                file_path=file_path,
                parse_status=ParseStatus.ERROR,
                error_count=len(error_spans),
                error_spans=error_spans,
            )
        ]

    # ------------------------------------------------------------------
    # Symbol extraction helpers
    # ------------------------------------------------------------------

    def _walk_for_symbols(
        self,
        node: object,
        source_code: str,
        file_path: str,
        symbols: list[Symbol],
        class_stack: list[str],
    ) -> None:
        """Recursively walk the AST and collect symbols."""
        ntype = node.type  # type: ignore[attr-defined]

        if ntype == "class_definition":
            sym = self._extract_class_symbol(node, source_code, file_path, class_stack)
            if sym is not None:
                symbols.append(sym)
            class_name = self._node_name(node)
            if class_name:
                class_stack.append(class_name)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_symbols(child, source_code, file_path, symbols, class_stack)
            if class_name:
                class_stack.pop()
            return

        if ntype == "decorated_definition":
            decorators = self._extract_decorators(node)
            inner = self._get_inner_definition(node)
            if inner is not None and inner.type == "class_definition":
                sym = self._extract_class_symbol(inner, source_code, file_path, class_stack, decorators)
                if sym is not None:
                    symbols.append(sym)
                class_name = self._node_name(inner)
                if class_name:
                    class_stack.append(class_name)
                for child in inner.children:
                    self._walk_for_symbols(child, source_code, file_path, symbols, class_stack)
                if class_name:
                    class_stack.pop()
            elif inner is not None and inner.type == "function_definition":
                sym = self._extract_function_symbol(inner, source_code, file_path, class_stack, decorators)
                if sym is not None:
                    symbols.append(sym)
                for child in inner.children:
                    if child.type == "block":
                        for block_child in child.children:
                            self._walk_for_symbols(block_child, source_code, file_path, symbols, class_stack)
            return

        if ntype == "function_definition":
            sym = self._extract_function_symbol(node, source_code, file_path, class_stack)
            if sym is not None:
                symbols.append(sym)
            for child in node.children:  # type: ignore[attr-defined]
                if child.type == "block":
                    for block_child in child.children:
                        self._walk_for_symbols(block_child, source_code, file_path, symbols, class_stack)
            return

        for child in node.children:  # type: ignore[attr-defined]
            self._walk_for_symbols(child, source_code, file_path, symbols, class_stack)

    def _extract_function_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
        class_stack: list[str],
        decorators: Optional[list[str]] = None,
    ) -> Optional[Symbol]:
        name = self._node_name(node)
        if name is None:
            return None

        kind = SymbolKind.METHOD if class_stack else SymbolKind.FUNCTION
        container_name = class_stack[-1] if class_stack else None
        signature = self._extract_function_signature(node, source_code)
        docstring = self._extract_docstring(node)
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]

        return Symbol(
            name=name,
            kind=kind,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            language=self.LANGUAGE,
            container_name=container_name,
            docstring=docstring,
        )

    def _extract_class_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
        class_stack: list[str],
        decorators: Optional[list[str]] = None,
    ) -> Optional[Symbol]:
        name = self._node_name(node)
        if name is None:
            return None

        container_name = class_stack[-1] if class_stack else None
        signature = self._extract_class_signature(node, source_code)
        docstring = self._extract_docstring(node)
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]

        return Symbol(
            name=name,
            kind=SymbolKind.CLASS,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            language=self.LANGUAGE,
            container_name=container_name,
            docstring=docstring,
        )

    def _extract_function_signature(self, node: object, source_code: str) -> str:
        """Reconstruct signature from function definition up to the colon."""
        return_type_node = None
        params_node = None
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "parameters":
                params_node = child
            elif child.type == "type":
                return_type_node = child

        if return_type_node is not None:
            rt_end_byte = return_type_node.end_byte - node.start_byte  # type: ignore[attr-defined]
            sig_bytes = node.text[:rt_end_byte]  # type: ignore[attr-defined]
            return sig_bytes.decode("utf-8").rstrip()
        elif params_node is not None:
            params_end_byte = params_node.end_byte - node.start_byte  # type: ignore[attr-defined]
            sig_bytes = node.text[:params_end_byte]  # type: ignore[attr-defined]
            return sig_bytes.decode("utf-8").rstrip()
        else:
            text = node.text.decode("utf-8")  # type: ignore[attr-defined]
            return text.split("\n")[0].rstrip().rstrip(":")

    def _extract_class_signature(self, node: object, source_code: str) -> str:
        """Reconstruct class signature: 'class Name(bases)'."""
        arg_list = None
        name_node = None
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "argument_list":
                arg_list = child
            elif child.type == "identifier":
                name_node = child

        if arg_list is not None:
            end_byte = arg_list.end_byte - node.start_byte  # type: ignore[attr-defined]
            return node.text[:end_byte].decode("utf-8").rstrip()  # type: ignore[attr-defined]
        elif name_node is not None:
            end_byte = name_node.end_byte - node.start_byte  # type: ignore[attr-defined]
            return node.text[:end_byte].decode("utf-8").rstrip()  # type: ignore[attr-defined]
        text = node.text.decode("utf-8")  # type: ignore[attr-defined]
        return text.split("\n")[0].rstrip().rstrip(":")

    def _extract_docstring(self, node: object) -> Optional[str]:
        """Extract docstring from the first expression_statement in a function/class body."""
        block = None
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "block":
                block = child
                break
        if block is None:
            return None

        for child in block.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        raw = sub.text.decode("utf-8")  # type: ignore[attr-defined]
                        return self._clean_docstring(raw)
                break
            elif child.type != "comment":
                break
        return None

    @staticmethod
    def _clean_docstring(raw: str) -> str:
        """Strip quotes from a docstring literal."""
        for quote in ('"""', "'''"):
            if raw.startswith(quote) and raw.endswith(quote):
                return raw[3:-3].strip()
        for quote in ('"', "'"):
            if raw.startswith(quote) and raw.endswith(quote):
                return raw[1:-1].strip()
        return raw.strip()

    def _extract_decorators(self, decorated_node: object) -> list[str]:
        """Extract decorator names from a decorated_definition node."""
        decorators: list[str] = []
        for child in decorated_node.children:  # type: ignore[attr-defined]
            if child.type == "decorator":
                dec_text = child.text.decode("utf-8").lstrip("@").strip()  # type: ignore[attr-defined]
                decorators.append(dec_text)
        return decorators

    def _get_inner_definition(self, decorated_node: object) -> Optional[object]:
        """Get the function_definition or class_definition inside a decorated_definition."""
        for child in decorated_node.children:  # type: ignore[attr-defined]
            if child.type in ("function_definition", "class_definition"):
                return child
        return None

    @staticmethod
    def _node_name(node: object) -> Optional[str]:
        """Get the name identifier from a function/class definition."""
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "identifier":
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
        return None

    # ------------------------------------------------------------------
    # Edge extraction helpers
    # ------------------------------------------------------------------

    def _walk_for_edges(
        self,
        node: object,
        source_code: str,
        file_path: str,
        symbols: list[Symbol],
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Recursively walk the AST and collect edges."""
        ntype = node.type  # type: ignore[attr-defined]

        if ntype in ("function_definition", "class_definition"):
            name = self._node_name(node)
            if name:
                scope_stack.append(name)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            if name:
                scope_stack.pop()
            return

        if ntype == "decorated_definition":
            inner = self._get_inner_definition(node)
            if inner is not None:
                name = self._node_name(inner)
                if name:
                    scope_stack.append(name)
                for child in inner.children:
                    self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
                if name:
                    scope_stack.pop()
            return

        if ntype == "import_statement":
            self._extract_import_edge(node, file_path, symbols, edges, scope_stack)
            return

        if ntype == "import_from_statement":
            self._extract_from_import_edges(node, file_path, symbols, edges, scope_stack)
            return

        if ntype == "call":
            self._extract_call_edge(node, file_path, symbols, edges, scope_stack)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            return

        if ntype == "argument_list":
            parent = node.parent  # type: ignore[attr-defined]
            if parent is not None and parent.type == "class_definition":
                self._extract_inheritance_edges(node, parent, file_path, symbols, edges, scope_stack)
                return

        for child in node.children:  # type: ignore[attr-defined]
            self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)

    def _resolve_source_symbol_id(self, scope_stack: list[str], file_path: str) -> str:
        """Build a source_symbol_id from current scope stack."""
        if scope_stack:
            return f"{file_path}:{scope_stack[-1]}"
        return f"{file_path}:<module>"

    def _extract_import_edge(
        self,
        node: object,
        file_path: str,
        symbols: list[Symbol],
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Handle 'import x' statements."""
        source_id = self._resolve_source_symbol_id(scope_stack, file_path)
        ref_text = node.text.decode("utf-8").strip()  # type: ignore[attr-defined]
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]
        column = node.start_point[1]  # type: ignore[attr-defined]

        edges.append(Edge(
            source_symbol_id=source_id,
            kind=EdgeKind.IMPORTS,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            column=column,
            ref_text=ref_text,
        ))

    def _extract_from_import_edges(
        self,
        node: object,
        file_path: str,
        symbols: list[Symbol],
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Handle 'from x import y, z' statements."""
        source_id = self._resolve_source_symbol_id(scope_stack, file_path)
        ref_text = node.text.decode("utf-8").strip()  # type: ignore[attr-defined]
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]
        column = node.start_point[1]  # type: ignore[attr-defined]

        imported_names: list[str] = []
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "dotted_name":
                imported_names.append(child.text.decode("utf-8"))
            elif child.type == "aliased_import":
                imported_names.append(child.text.decode("utf-8"))

        if not imported_names:
            edges.append(Edge(
                source_symbol_id=source_id,
                kind=EdgeKind.IMPORTS,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                column=column,
                ref_text=ref_text,
            ))
            return

        module_name = imported_names[0] if imported_names else ""
        imported = imported_names[1:] if len(imported_names) > 1 else imported_names

        for name in imported:
            edge_ref = f"from {module_name} import {name}" if module_name and name != module_name else ref_text
            edges.append(Edge(
                source_symbol_id=source_id,
                kind=EdgeKind.IMPORTS,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                column=column,
                ref_text=edge_ref,
            ))

    def _extract_call_edge(
        self,
        node: object,
        file_path: str,
        symbols: list[Symbol],
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Handle call expressions."""
        source_id = self._resolve_source_symbol_id(scope_stack, file_path)
        ref_text = node.text.decode("utf-8").strip()  # type: ignore[attr-defined]
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]
        column = node.start_point[1]  # type: ignore[attr-defined]

        edges.append(Edge(
            source_symbol_id=source_id,
            kind=EdgeKind.CALLS,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            column=column,
            ref_text=ref_text,
        ))

    def _extract_inheritance_edges(
        self,
        arg_list_node: object,
        class_node: object,
        file_path: str,
        symbols: list[Symbol],
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Handle class inheritance (base classes)."""
        class_name = self._node_name(class_node)
        if class_name is None:
            return

        source_id = self._resolve_source_symbol_id(scope_stack, file_path)
        start_line = class_node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = class_node.end_point[0] + 1  # type: ignore[attr-defined]
        column = class_node.start_point[1]  # type: ignore[attr-defined]

        for child in arg_list_node.children:  # type: ignore[attr-defined]
            if child.type in ("identifier", "attribute"):
                base_name = child.text.decode("utf-8")  # type: ignore[attr-defined]
                edges.append(Edge(
                    source_symbol_id=source_id,
                    kind=EdgeKind.INHERITS,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    column=column,
                    ref_text=base_name,
                ))

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _collect_errors(self, node: object) -> list[dict]:
        """Walk the tree and collect ERROR / MISSING nodes."""
        errors: list[dict] = []
        self._walk_for_errors(node, errors)
        return errors

    def _walk_for_errors(self, node: object, errors: list[dict]) -> None:
        if node.type == "ERROR" or node.is_missing:  # type: ignore[attr-defined]
            errors.append({
                "start_line": node.start_point[0] + 1,  # type: ignore[attr-defined]
                "start_column": node.start_point[1],  # type: ignore[attr-defined]
                "end_line": node.end_point[0] + 1,  # type: ignore[attr-defined]
                "end_column": node.end_point[1],  # type: ignore[attr-defined]
                "type": "error" if node.type == "ERROR" else "missing",  # type: ignore[attr-defined]
            })
        for child in node.children:  # type: ignore[attr-defined]
            self._walk_for_errors(child, errors)
