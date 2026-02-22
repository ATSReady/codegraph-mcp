"""JavaScript/JSX tree-sitter extractor."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import Edge, EdgeKind, Symbol, SymbolKind
from codegraph.domain.workspace import FileDiagnostic
from codegraph.infrastructure.parsers.extractors.typescript_extractor import TypeScriptExtractor


class JavaScriptExtractor(TypeScriptExtractor):
    """Extract symbols, edges, and diagnostics from JavaScript/JSX source.

    Inherits from TypeScriptExtractor but skips TypeScript-specific constructs
    (interfaces, type aliases, enums) and adds CommonJS require() support.
    """

    LANGUAGE = "javascript"

    # ------------------------------------------------------------------
    # Override symbol walk to skip TS-specific nodes
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

        # Skip TS-specific declarations (they won't normally appear in JS,
        # but if tree-sitter somehow parses them, ignore them)
        if ntype in ("interface_declaration", "type_alias_declaration", "enum_declaration"):
            return

        super()._walk_for_symbols(node, source_code, file_path, symbols, class_stack)

    # ------------------------------------------------------------------
    # Override edge walk to add require() support
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

        # Intercept call_expression to detect require() calls
        if ntype == "call_expression":
            if self._is_require_call(node):
                self._extract_require_edge(node, file_path, edges, scope_stack)
                return
            # Not a require() — delegate to parent for normal call edge
            super()._walk_for_edges(node, source_code, file_path, symbols, edges, scope_stack)
            return

        super()._walk_for_edges(node, source_code, file_path, symbols, edges, scope_stack)

    @staticmethod
    def _is_require_call(node: object) -> bool:
        """Check if a call_expression is a require('...') call."""
        children = node.children  # type: ignore[attr-defined]
        if not children:
            return False
        func_node = children[0]
        return (
            func_node.type == "identifier"
            and func_node.text.decode("utf-8") == "require"  # type: ignore[attr-defined]
        )
