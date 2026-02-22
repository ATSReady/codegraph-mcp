"""TypeScript/TSX tree-sitter extractor."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import Edge, EdgeKind, Symbol, SymbolKind
from codegraph.domain.workspace import FileDiagnostic, ParseStatus
from codegraph.infrastructure.parsers.extractors.base import LanguageExtractor


class TypeScriptExtractor(LanguageExtractor):
    """Extract symbols, edges, and diagnostics from TypeScript/TSX source."""

    LANGUAGE = "typescript"

    # Node types that represent function-like declarations at the top level
    _FUNCTION_NODE_TYPES = frozenset({
        "function_declaration",
        "generator_function_declaration",
    })

    # Variable declaration keywords that can hold arrow functions
    _VAR_DECL_TYPES = frozenset({
        "lexical_declaration",   # const, let
        "variable_declaration",  # var
    })

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
    # Symbol extraction
    # ------------------------------------------------------------------

    def _walk_for_symbols(
        self,
        node: object,
        source_code: str,
        file_path: str,
        symbols: list[Symbol],
        class_stack: list[str],
    ) -> None:
        ntype = node.type  # type: ignore[attr-defined]

        # export_statement wraps declarations — unwrap and recurse
        if ntype == "export_statement":
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_symbols(child, source_code, file_path, symbols, class_stack)
            return

        # --- Functions ---
        if ntype in self._FUNCTION_NODE_TYPES:
            sym = self._extract_function_symbol(node, source_code, file_path, class_stack)
            if sym is not None:
                symbols.append(sym)
            # Recurse into body for nested definitions
            self._recurse_into_body(node, source_code, file_path, symbols, class_stack)
            return

        # --- Arrow functions / function expressions assigned to variables ---
        if ntype in self._VAR_DECL_TYPES:
            self._extract_var_decl_functions(node, source_code, file_path, symbols, class_stack)
            # Still recurse for nested definitions
            for child in node.children:  # type: ignore[attr-defined]
                if child.type == "variable_declarator":
                    for sub in child.children:  # type: ignore[attr-defined]
                        if sub.type in ("arrow_function", "function"):
                            self._recurse_into_body(sub, source_code, file_path, symbols, class_stack)
            return

        # --- Classes ---
        if ntype == "class_declaration":
            sym = self._extract_class_symbol(node, source_code, file_path, class_stack)
            if sym is not None:
                symbols.append(sym)
            class_name = self._node_type_name(node)
            if class_name:
                class_stack.append(class_name)
                self._extract_class_members(node, source_code, file_path, symbols, class_stack)
                class_stack.pop()
            return

        # --- Interfaces ---
        if ntype == "interface_declaration":
            sym = self._extract_interface_symbol(node, source_code, file_path)
            if sym is not None:
                symbols.append(sym)
            return

        # --- Type aliases ---
        if ntype == "type_alias_declaration":
            sym = self._extract_type_alias_symbol(node, source_code, file_path)
            if sym is not None:
                symbols.append(sym)
            return

        # --- Enums ---
        if ntype == "enum_declaration":
            sym = self._extract_enum_symbol(node, source_code, file_path)
            if sym is not None:
                symbols.append(sym)
            return

        # --- Method definitions (inside class body) ---
        if ntype == "method_definition" and class_stack:
            sym = self._extract_method_symbol(node, source_code, file_path, class_stack)
            if sym is not None:
                symbols.append(sym)
            self._recurse_into_body(node, source_code, file_path, symbols, class_stack)
            return

        # Default: recurse into children
        for child in node.children:  # type: ignore[attr-defined]
            self._walk_for_symbols(child, source_code, file_path, symbols, class_stack)

    def _extract_function_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
        class_stack: list[str],
    ) -> Optional[Symbol]:
        name = self._node_name(node)
        if name is None:
            return None

        kind = SymbolKind.METHOD if class_stack else SymbolKind.FUNCTION
        container_name = class_stack[-1] if class_stack else None
        signature = self._build_function_signature(node, source_code)
        docstring = self._extract_jsdoc(node)
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

    def _extract_var_decl_functions(
        self,
        node: object,
        source_code: str,
        file_path: str,
        symbols: list[Symbol],
        class_stack: list[str],
    ) -> None:
        """Extract arrow functions or function expressions assigned to const/let/var."""
        for child in node.children:  # type: ignore[attr-defined]
            if child.type != "variable_declarator":
                continue
            var_name: Optional[str] = None
            func_node: Optional[object] = None
            for sub in child.children:  # type: ignore[attr-defined]
                if sub.type == "identifier":
                    var_name = sub.text.decode("utf-8")  # type: ignore[attr-defined]
                elif sub.type in ("arrow_function", "function"):
                    func_node = sub

            if var_name is None or func_node is None:
                continue

            signature = self._build_arrow_signature(var_name, func_node, source_code)
            docstring = self._extract_jsdoc(node)
            # Use the full lexical_declaration span
            start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
            end_line = node.end_point[0] + 1  # type: ignore[attr-defined]

            kind = SymbolKind.METHOD if class_stack else SymbolKind.FUNCTION
            container_name = class_stack[-1] if class_stack else None

            symbols.append(Symbol(
                name=var_name,
                kind=kind,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                signature=signature,
                language=self.LANGUAGE,
                container_name=container_name,
                docstring=docstring,
            ))

    def _extract_class_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
        class_stack: list[str],
    ) -> Optional[Symbol]:
        name = self._node_type_name(node)
        if name is None:
            return None

        container_name = class_stack[-1] if class_stack else None
        signature = self._build_class_signature(node, source_code)
        docstring = self._extract_jsdoc(node)
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

    def _extract_class_members(
        self,
        class_node: object,
        source_code: str,
        file_path: str,
        symbols: list[Symbol],
        class_stack: list[str],
    ) -> None:
        """Walk class_body children to extract methods."""
        for child in class_node.children:  # type: ignore[attr-defined]
            if child.type == "class_body":
                for member in child.children:  # type: ignore[attr-defined]
                    if member.type == "method_definition":
                        sym = self._extract_method_symbol(member, source_code, file_path, class_stack)
                        if sym is not None:
                            symbols.append(sym)
                        self._recurse_into_body(member, source_code, file_path, symbols, class_stack)

    def _extract_method_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
        class_stack: list[str],
    ) -> Optional[Symbol]:
        name = self._method_name(node)
        if name is None:
            return None

        container_name = class_stack[-1] if class_stack else None
        signature = self._build_method_signature(node, source_code)
        docstring = self._extract_jsdoc(node)
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]

        return Symbol(
            name=name,
            kind=SymbolKind.METHOD,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            language=self.LANGUAGE,
            container_name=container_name,
            docstring=docstring,
        )

    def _extract_interface_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
    ) -> Optional[Symbol]:
        name = self._node_type_name(node)
        if name is None:
            return None

        signature = self._build_interface_signature(node, source_code)
        docstring = self._extract_jsdoc(node)
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]

        return Symbol(
            name=name,
            kind=SymbolKind.INTERFACE,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            language=self.LANGUAGE,
            docstring=docstring,
        )

    def _extract_type_alias_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
    ) -> Optional[Symbol]:
        name = self._node_type_name(node)
        if name is None:
            return None

        text = node.text.decode("utf-8").rstrip(";").strip()  # type: ignore[attr-defined]
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]

        return Symbol(
            name=name,
            kind=SymbolKind.TYPE_ALIAS,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=text,
            language=self.LANGUAGE,
        )

    def _extract_enum_symbol(
        self,
        node: object,
        source_code: str,
        file_path: str,
    ) -> Optional[Symbol]:
        name = self._node_name(node)
        if name is None:
            return None

        first_line = node.text.decode("utf-8").split("\n")[0].rstrip()  # type: ignore[attr-defined]
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]

        return Symbol(
            name=name,
            kind=SymbolKind.ENUM,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=first_line,
            language=self.LANGUAGE,
        )

    # ------------------------------------------------------------------
    # Signature builders
    # ------------------------------------------------------------------

    def _build_function_signature(self, node: object, source_code: str) -> str:
        """Build signature for function_declaration / generator_function_declaration."""
        # Capture up through type_annotation (return type) or formal_parameters
        last_offset = 0
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "type_annotation":
                last_offset = child.end_byte - node.start_byte  # type: ignore[attr-defined]
            elif child.type == "formal_parameters":
                if last_offset == 0:
                    last_offset = child.end_byte - node.start_byte  # type: ignore[attr-defined]

        if last_offset > 0:
            return node.text[:last_offset].decode("utf-8").rstrip()  # type: ignore[attr-defined]

        # Fallback: first line
        return node.text.decode("utf-8").split("\n")[0].rstrip()  # type: ignore[attr-defined]

    def _build_arrow_signature(self, name: str, func_node: object, source_code: str) -> str:
        """Build signature for arrow functions: 'const name = (params): type => ...'."""
        params_text = ""
        return_type_text = ""
        for child in func_node.children:  # type: ignore[attr-defined]
            if child.type == "formal_parameters":
                params_text = child.text.decode("utf-8")  # type: ignore[attr-defined]
            elif child.type == "type_annotation":
                return_type_text = child.text.decode("utf-8")  # type: ignore[attr-defined]

        sig = f"const {name} = {params_text}"
        if return_type_text:
            sig += return_type_text
        return sig

    def _build_class_signature(self, node: object, source_code: str) -> str:
        """Build class signature: 'class Name extends Foo implements Bar'."""
        parts: list[str] = ["class"]
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "type_identifier":
                parts.append(child.text.decode("utf-8"))  # type: ignore[attr-defined]
            elif child.type == "class_heritage":
                parts.append(child.text.decode("utf-8"))  # type: ignore[attr-defined]
            elif child.type == "class_body":
                break
        return " ".join(parts)

    def _build_method_signature(self, node: object, source_code: str) -> str:
        """Build method signature up to return type or params end."""
        last_offset = 0
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "type_annotation":
                last_offset = child.end_byte - node.start_byte  # type: ignore[attr-defined]
            elif child.type == "formal_parameters":
                if last_offset == 0:
                    last_offset = child.end_byte - node.start_byte  # type: ignore[attr-defined]

        if last_offset > 0:
            return node.text[:last_offset].decode("utf-8").rstrip()  # type: ignore[attr-defined]

        return node.text.decode("utf-8").split("\n")[0].rstrip()  # type: ignore[attr-defined]

    def _build_interface_signature(self, node: object, source_code: str) -> str:
        """Build interface signature: 'interface Name extends Base'."""
        parts: list[str] = ["interface"]
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "type_identifier":
                parts.append(child.text.decode("utf-8"))  # type: ignore[attr-defined]
            elif child.type == "extends_type_clause":
                parts.append(child.text.decode("utf-8"))  # type: ignore[attr-defined]
            elif child.type == "object_type":
                break
        return " ".join(parts)

    # ------------------------------------------------------------------
    # JSDoc extraction
    # ------------------------------------------------------------------

    def _extract_jsdoc(self, node: object) -> Optional[str]:
        """Extract a JSDoc comment that immediately precedes this node."""
        prev = node.prev_sibling  # type: ignore[attr-defined]
        if prev is None:
            # Check parent (e.g. export_statement wrapping)
            parent = node.parent  # type: ignore[attr-defined]
            if parent is not None:
                prev = parent.prev_sibling  # type: ignore[attr-defined]
        if prev is None or prev.type != "comment":  # type: ignore[attr-defined]
            return None
        text = prev.text.decode("utf-8").strip()  # type: ignore[attr-defined]
        if not text.startswith("/**"):
            return None
        return self._clean_jsdoc(text)

    @staticmethod
    def _clean_jsdoc(raw: str) -> str:
        """Clean JSDoc comment: strip delimiters and leading asterisks."""
        # Remove /** and */
        inner = raw
        if inner.startswith("/**"):
            inner = inner[3:]
        if inner.endswith("*/"):
            inner = inner[:-2]
        # Strip leading * from each line
        lines = []
        for line in inner.split("\n"):
            stripped = line.strip()
            if stripped.startswith("*"):
                stripped = stripped[1:].strip()
            lines.append(stripped)
        result = "\n".join(lines).strip()
        return result

    # ------------------------------------------------------------------
    # Edge extraction
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
        ntype = node.type  # type: ignore[attr-defined]

        # Track scope for source_symbol_id
        if ntype in self._FUNCTION_NODE_TYPES or ntype == "generator_function_declaration":
            name = self._node_name(node)
            if name:
                scope_stack.append(name)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            if name:
                scope_stack.pop()
            return

        if ntype == "class_declaration":
            name = self._node_type_name(node)
            if name:
                scope_stack.append(name)
            # Extract inheritance edges from class_heritage
            self._extract_class_heritage_edges(node, file_path, edges, scope_stack)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            if name:
                scope_stack.pop()
            return

        if ntype == "method_definition":
            name = self._method_name(node)
            if name:
                scope_stack.append(name)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            if name:
                scope_stack.pop()
            return

        if ntype == "export_statement":
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            return

        if ntype == "import_statement":
            self._extract_import_edges(node, file_path, edges, scope_stack)
            return

        if ntype == "call_expression":
            self._extract_call_edge(node, file_path, edges, scope_stack)
            # Continue recursing for nested calls
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            return

        # Arrow functions inside variable declarations — track scope
        if ntype in self._VAR_DECL_TYPES:
            for child in node.children:  # type: ignore[attr-defined]
                if child.type == "variable_declarator":
                    var_name: Optional[str] = None
                    func_child: Optional[object] = None
                    for sub in child.children:  # type: ignore[attr-defined]
                        if sub.type == "identifier":
                            var_name = sub.text.decode("utf-8")  # type: ignore[attr-defined]
                        elif sub.type in ("arrow_function", "function"):
                            func_child = sub
                    if var_name and func_child:
                        scope_stack.append(var_name)
                        for sub in func_child.children:  # type: ignore[attr-defined]
                            self._walk_for_edges(sub, source_code, file_path, symbols, edges, scope_stack)
                        scope_stack.pop()
                    else:
                        # Not an arrow function var decl, still recurse
                        self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
                else:
                    self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            return

        for child in node.children:  # type: ignore[attr-defined]
            self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)

    def _resolve_source_symbol_id(self, scope_stack: list[str], file_path: str) -> str:
        if scope_stack:
            return f"{file_path}:{scope_stack[-1]}"
        return f"{file_path}:<module>"

    def _extract_import_edges(
        self,
        node: object,
        file_path: str,
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Handle ES6 import statements."""
        source_id = self._resolve_source_symbol_id(scope_stack, file_path)
        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]
        column = node.start_point[1]  # type: ignore[attr-defined]

        # Find the module specifier (string node after 'from')
        module_name = self._extract_import_module(node)

        # Find all imported names
        imported_names: list[str] = []
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "import_clause":
                for sub in child.children:  # type: ignore[attr-defined]
                    if sub.type == "identifier":
                        # default import
                        imported_names.append(sub.text.decode("utf-8"))  # type: ignore[attr-defined]
                    elif sub.type == "named_imports":
                        for imp in sub.children:  # type: ignore[attr-defined]
                            if imp.type == "import_specifier":
                                spec_name = imp.children[0].text.decode("utf-8") if imp.children else ""  # type: ignore[attr-defined]
                                imported_names.append(spec_name)
                    elif sub.type == "namespace_import":
                        # import * as name
                        for ns_child in sub.children:  # type: ignore[attr-defined]
                            if ns_child.type == "identifier":
                                imported_names.append(f"* as {ns_child.text.decode('utf-8')}")  # type: ignore[attr-defined]

        if not imported_names:
            # Side-effect import: import 'module'
            ref_text = node.text.decode("utf-8").strip()  # type: ignore[attr-defined]
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

        for name in imported_names:
            ref = f"import {name} from '{module_name}'" if module_name else f"import {name}"
            edges.append(Edge(
                source_symbol_id=source_id,
                kind=EdgeKind.IMPORTS,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                column=column,
                ref_text=ref,
            ))

    def _extract_import_module(self, node: object) -> str:
        """Extract the module specifier string from an import statement."""
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "string":
                # String node has children: quote, string_fragment, quote
                for sub in child.children:  # type: ignore[attr-defined]
                    if sub.type == "string_fragment":
                        return sub.text.decode("utf-8")  # type: ignore[attr-defined]
                # Fallback: strip quotes
                raw = child.text.decode("utf-8")  # type: ignore[attr-defined]
                return raw.strip("'\"")
        return ""

    def _extract_call_edge(
        self,
        node: object,
        file_path: str,
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
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

    def _extract_class_heritage_edges(
        self,
        class_node: object,
        file_path: str,
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Extract INHERITS and IMPLEMENTS edges from class_heritage.

        Handles both TypeScript grammar (with extends_clause/implements_clause
        wrapper nodes) and JavaScript grammar (where class_heritage directly
        contains 'extends' keyword + identifier).
        """
        source_id = self._resolve_source_symbol_id(scope_stack, file_path)
        start_line = class_node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = class_node.end_point[0] + 1  # type: ignore[attr-defined]
        column = class_node.start_point[1]  # type: ignore[attr-defined]

        for child in class_node.children:  # type: ignore[attr-defined]
            if child.type != "class_heritage":
                continue

            has_extends_clause = any(
                c.type in ("extends_clause", "implements_clause")
                for c in child.children  # type: ignore[attr-defined]
            )

            if has_extends_clause:
                # TypeScript grammar: class_heritage > extends_clause / implements_clause
                for heritage_child in child.children:  # type: ignore[attr-defined]
                    if heritage_child.type == "extends_clause":
                        for ext_child in heritage_child.children:  # type: ignore[attr-defined]
                            if ext_child.type in ("identifier", "type_identifier", "member_expression"):
                                base_name = ext_child.text.decode("utf-8")  # type: ignore[attr-defined]
                                edges.append(Edge(
                                    source_symbol_id=source_id,
                                    kind=EdgeKind.INHERITS,
                                    file_path=file_path,
                                    start_line=start_line,
                                    end_line=end_line,
                                    column=column,
                                    ref_text=base_name,
                                ))
                    elif heritage_child.type == "implements_clause":
                        for impl_child in heritage_child.children:  # type: ignore[attr-defined]
                            if impl_child.type in ("identifier", "type_identifier", "member_expression"):
                                iface_name = impl_child.text.decode("utf-8")  # type: ignore[attr-defined]
                                edges.append(Edge(
                                    source_symbol_id=source_id,
                                    kind=EdgeKind.IMPLEMENTS,
                                    file_path=file_path,
                                    start_line=start_line,
                                    end_line=end_line,
                                    column=column,
                                    ref_text=iface_name,
                                ))
            else:
                # JavaScript grammar: class_heritage directly has 'extends' + identifier
                saw_extends = False
                for heritage_child in child.children:  # type: ignore[attr-defined]
                    if heritage_child.type == "extends":
                        saw_extends = True
                    elif saw_extends and heritage_child.type in ("identifier", "member_expression"):
                        base_name = heritage_child.text.decode("utf-8")  # type: ignore[attr-defined]
                        edges.append(Edge(
                            source_symbol_id=source_id,
                            kind=EdgeKind.INHERITS,
                            file_path=file_path,
                            start_line=start_line,
                            end_line=end_line,
                            column=column,
                            ref_text=base_name,
                        ))

    def _extract_require_edge(
        self,
        node: object,
        file_path: str,
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        """Extract an IMPORTS edge from a require() call expression."""
        # Check if this is require('...')
        func_node = node.children[0] if node.children else None  # type: ignore[attr-defined]
        if func_node is None:
            return
        if func_node.type != "identifier" or func_node.text.decode("utf-8") != "require":  # type: ignore[attr-defined]
            return

        # Get the module string from arguments
        args_node = None
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "arguments":
                args_node = child
                break
        if args_node is None:
            return

        module_name = ""
        for arg in args_node.children:  # type: ignore[attr-defined]
            if arg.type == "string":
                for sub in arg.children:  # type: ignore[attr-defined]
                    if sub.type == "string_fragment":
                        module_name = sub.text.decode("utf-8")  # type: ignore[attr-defined]
                        break
                if not module_name:
                    module_name = arg.text.decode("utf-8").strip("'\"")  # type: ignore[attr-defined]
                break

        if not module_name:
            return

        source_id = self._resolve_source_symbol_id(scope_stack, file_path)
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
            ref_text=f"require('{module_name}')",
        ))

    # ------------------------------------------------------------------
    # Node helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _node_name(node: object) -> Optional[str]:
        """Get the 'identifier' child text."""
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "identifier":
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
        return None

    @staticmethod
    def _node_type_name(node: object) -> Optional[str]:
        """Get the 'type_identifier' child text (used for classes, interfaces, types)."""
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "type_identifier":
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
        # Fallback to identifier (some nodes use identifier instead)
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "identifier":
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
        return None

    @staticmethod
    def _method_name(node: object) -> Optional[str]:
        """Get method name from a method_definition node."""
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "property_identifier":
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
            # constructor, get, set can appear as keywords
            if child.type in ("identifier",):
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
        return None

    def _recurse_into_body(
        self,
        node: object,
        source_code: str,
        file_path: str,
        symbols: list[Symbol],
        class_stack: list[str],
    ) -> None:
        """Recurse into statement_block children for nested definitions."""
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "statement_block":
                for block_child in child.children:  # type: ignore[attr-defined]
                    self._walk_for_symbols(block_child, source_code, file_path, symbols, class_stack)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def _collect_errors(self, node: object) -> list[dict]:
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
