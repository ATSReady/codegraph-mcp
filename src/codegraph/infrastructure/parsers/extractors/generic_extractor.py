"""Generic tree-sitter extractor fallback for unsupported languages.

Uses common node type patterns that work across many languages (Go, Rust,
Java, C, C++, Ruby, PHP, Swift, Kotlin, etc.) to provide reasonable
structural extraction when no specialized extractor exists.
"""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import Edge, EdgeKind, Symbol, SymbolKind
from codegraph.domain.workspace import FileDiagnostic, ParseStatus
from codegraph.infrastructure.parsers.extractors.base import LanguageExtractor

# Node types that map to symbol kinds.
_FUNCTION_NODE_TYPES = frozenset({
    "function_definition",
    "function_declaration",
    "method_definition",
    "method_declaration",
    "function_item",          # Rust
})

_CLASS_NODE_TYPES = frozenset({
    "class_definition",
    "class_declaration",
    "struct_item",           # Rust
    "struct_specifier",      # C/C++
})

_INTERFACE_NODE_TYPES = frozenset({
    "interface_declaration",
})

_ENUM_NODE_TYPES = frozenset({
    "enum_declaration",
    "enum_definition",
    "enum_item",             # Rust
    "enum_specifier",        # C/C++
})

_TYPE_ALIAS_NODE_TYPES = frozenset({
    "type_alias_declaration",
    "type_definition",
    "type_declaration",      # Go
    "type_spec",             # Go (nested inside type_declaration)
    "type_item",             # Rust
})

# Container node types -- if a function is nested inside one of these, it
# becomes a METHOD with container_name set.
_CONTAINER_NODE_TYPES = (
    _CLASS_NODE_TYPES
    | _INTERFACE_NODE_TYPES
    | frozenset({
        "impl_item",              # Rust impl blocks
        "object_declaration",     # Kotlin
    })
)

# Node types that represent call expressions.
_CALL_NODE_TYPES = frozenset({
    "call_expression",
    "method_invocation",      # Java
    "invocation_expression",  # C#
})

# Node types that represent import statements.
_IMPORT_NODE_TYPES = frozenset({
    "import_statement",
    "import_declaration",
    "use_declaration",        # Rust
    "include_directive",      # C/C++ #include
    "preproc_include",        # C/C++ preprocessor include
})

# Node types for name extraction.
_NAME_NODE_TYPES = frozenset({
    "identifier",
    "type_identifier",
    "field_identifier",
    "property_identifier",
})


class GenericExtractor(LanguageExtractor):
    """Fallback extractor using common tree-sitter node type patterns."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_symbols(self, tree: object, source_code: str, file_path: str) -> list[Symbol]:
        symbols: list[Symbol] = []
        root = tree.root_node  # type: ignore[attr-defined]
        language = self._guess_language(file_path)
        self._walk_for_symbols(root, source_code, file_path, language, symbols, container_stack=[])
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
        language: str,
        symbols: list[Symbol],
        container_stack: list[str],
    ) -> None:
        ntype = node.type  # type: ignore[attr-defined]

        # --- Container types (class, struct, interface, enum, impl) ---
        if ntype in _CLASS_NODE_TYPES:
            sym = self._make_symbol(
                node, SymbolKind.CLASS, file_path, language, container_stack,
            )
            if sym is not None:
                symbols.append(sym)
                container_stack.append(sym.name)
                self._walk_children(node, source_code, file_path, language, symbols, container_stack)
                container_stack.pop()
                return
            # If we could not get a name, still walk children
            self._walk_children(node, source_code, file_path, language, symbols, container_stack)
            return

        if ntype in _INTERFACE_NODE_TYPES:
            sym = self._make_symbol(
                node, SymbolKind.INTERFACE, file_path, language, container_stack,
            )
            if sym is not None:
                symbols.append(sym)
                container_stack.append(sym.name)
                self._walk_children(node, source_code, file_path, language, symbols, container_stack)
                container_stack.pop()
                return
            self._walk_children(node, source_code, file_path, language, symbols, container_stack)
            return

        if ntype in _ENUM_NODE_TYPES:
            sym = self._make_symbol(
                node, SymbolKind.CLASS, file_path, language, container_stack,
            )
            if sym is not None:
                symbols.append(sym)
            # Do not recurse into enum bodies for child symbols
            return

        if ntype in _TYPE_ALIAS_NODE_TYPES:
            sym = self._make_symbol(
                node, SymbolKind.TYPE, file_path, language, container_stack,
            )
            if sym is not None:
                symbols.append(sym)
                return
            # Name might be nested (e.g. Go type_declaration > type_spec),
            # so walk children to find it.
            self._walk_children(node, source_code, file_path, language, symbols, container_stack)
            return

        # --- Container-only nodes (e.g. Rust impl) ---
        if ntype in _CONTAINER_NODE_TYPES and ntype not in _CLASS_NODE_TYPES and ntype not in _INTERFACE_NODE_TYPES:
            container_name = self._get_node_name(node)
            if container_name:
                container_stack.append(container_name)
                self._walk_children(node, source_code, file_path, language, symbols, container_stack)
                container_stack.pop()
                return
            # No name found, just walk children without pushing
            self._walk_children(node, source_code, file_path, language, symbols, container_stack)
            return

        # --- Function types ---
        if ntype in _FUNCTION_NODE_TYPES:
            kind = SymbolKind.METHOD if container_stack else SymbolKind.FUNCTION
            sym = self._make_symbol(node, kind, file_path, language, container_stack)
            if sym is not None:
                symbols.append(sym)
            # Walk into function body for nested definitions
            self._walk_children(node, source_code, file_path, language, symbols, container_stack)
            return

        # --- Default: recurse into children ---
        self._walk_children(node, source_code, file_path, language, symbols, container_stack)

    def _walk_children(
        self,
        node: object,
        source_code: str,
        file_path: str,
        language: str,
        symbols: list[Symbol],
        container_stack: list[str],
    ) -> None:
        for child in node.children:  # type: ignore[attr-defined]
            self._walk_for_symbols(child, source_code, file_path, language, symbols, container_stack)

    def _make_symbol(
        self,
        node: object,
        kind: SymbolKind,
        file_path: str,
        language: str,
        container_stack: list[str],
    ) -> Optional[Symbol]:
        name = self._get_node_name(node)
        if name is None:
            return None

        start_line = node.start_point[0] + 1  # type: ignore[attr-defined]
        end_line = node.end_point[0] + 1  # type: ignore[attr-defined]
        signature = self._extract_signature(node)
        container_name = container_stack[-1] if container_stack else None

        return Symbol(
            name=name,
            kind=kind,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            signature=signature,
            language=language,
            container_name=container_name,
        )

    def _extract_signature(self, node: object) -> str:
        """Extract signature from the node text up to the first body delimiter."""
        text = node.text.decode("utf-8")  # type: ignore[attr-defined]
        # Take the first line, or up to the first opening brace/colon
        first_line = text.split("\n")[0]
        # Trim at the opening brace if present (common in C-like languages)
        idx = first_line.find("{")
        if idx != -1:
            first_line = first_line[:idx]
        return first_line.rstrip().rstrip(":")

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

        # Track scope for function/class defs
        if ntype in _FUNCTION_NODE_TYPES | _CLASS_NODE_TYPES | _INTERFACE_NODE_TYPES:
            name = self._get_node_name(node)
            if name:
                scope_stack.append(name)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            if name:
                scope_stack.pop()
            return

        # Container-only nodes (e.g. Rust impl)
        if ntype in _CONTAINER_NODE_TYPES:
            name = self._get_node_name(node)
            if name:
                scope_stack.append(name)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            if name:
                scope_stack.pop()
            return

        # Call expressions
        if ntype in _CALL_NODE_TYPES:
            self._extract_call_edge(node, file_path, edges, scope_stack)
            for child in node.children:  # type: ignore[attr-defined]
                self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)
            return

        # Import statements
        if ntype in _IMPORT_NODE_TYPES:
            self._extract_import_edge(node, file_path, edges, scope_stack)
            return

        for child in node.children:  # type: ignore[attr-defined]
            self._walk_for_edges(child, source_code, file_path, symbols, edges, scope_stack)

    def _extract_call_edge(
        self,
        node: object,
        file_path: str,
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        source_id = self._resolve_source_id(scope_stack, file_path)
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

    def _extract_import_edge(
        self,
        node: object,
        file_path: str,
        edges: list[Edge],
        scope_stack: list[str],
    ) -> None:
        source_id = self._resolve_source_id(scope_stack, file_path)
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

    def _resolve_source_id(self, scope_stack: list[str], file_path: str) -> str:
        if scope_stack:
            return f"{file_path}:{scope_stack[-1]}"
        return f"{file_path}:<module>"

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_node_name(node: object) -> Optional[str]:
        """Get the name from the first identifier-like child node.

        Prioritises plain ``identifier`` over ``type_identifier`` so that
        Java-style method declarations (where the return-type comes before
        the method name) pick up the correct name.
        """
        # First pass: look for plain identifier / field_identifier
        for child in node.children:  # type: ignore[attr-defined]
            if child.type in ("identifier", "field_identifier", "property_identifier"):  # type: ignore[attr-defined]
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
        # Second pass: fall back to type_identifier (e.g. Rust struct names)
        for child in node.children:  # type: ignore[attr-defined]
            if child.type == "type_identifier":  # type: ignore[attr-defined]
                return child.text.decode("utf-8")  # type: ignore[attr-defined]
        return None

    @staticmethod
    def _guess_language(file_path: str) -> str:
        """Derive a language name from the file extension for the Symbol.language field."""
        from codegraph.infrastructure.parsers.languages import detect_language
        return detect_language(file_path) or "unknown"
