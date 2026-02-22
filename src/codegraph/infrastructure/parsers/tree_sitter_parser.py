"""Tree-sitter based code parser."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.models import Symbol, Edge
from codegraph.domain.workspace import FileDiagnostic
from codegraph.infrastructure.parsers.languages import detect_language, get_parser
from codegraph.infrastructure.parsers.extractors.base import LanguageExtractor
from codegraph.infrastructure.parsers.extractors.generic_extractor import GenericExtractor
from codegraph.infrastructure.parsers.extractors.python_extractor import PythonExtractor
from codegraph.infrastructure.parsers.extractors.typescript_extractor import TypeScriptExtractor
from codegraph.infrastructure.parsers.extractors.javascript_extractor import JavaScriptExtractor

# Map language aliases to the grammar name tree-sitter-languages actually supports.
_PARSER_LANGUAGE_MAP: dict[str, str] = {
    "jsx": "javascript",
}


class TreeSitterParser:
    """Parses source files using tree-sitter and language-specific extractors."""

    def __init__(self) -> None:
        self._extractors: dict[str, LanguageExtractor] = {
            "python": PythonExtractor(),
            "typescript": TypeScriptExtractor(),
            "tsx": TypeScriptExtractor(),  # TSX uses same extractor
            "javascript": JavaScriptExtractor(),
            "jsx": JavaScriptExtractor(),  # JSX uses same extractor
        }
        self._generic_extractor = GenericExtractor()

    def parse_file(
        self, file_path: str, source_code: str, language: Optional[str] = None,
    ) -> tuple[list[Symbol], list[Edge], list[FileDiagnostic]]:
        if language is None:
            language = detect_language(file_path)
        if language is None:
            return [], [], []

        # Resolve grammar alias (e.g. "jsx" -> "javascript")
        grammar_language = _PARSER_LANGUAGE_MAP.get(language, language)
        parser = get_parser(grammar_language)
        tree = parser.parse(source_code.encode("utf-8"))

        extractor = self._extractors.get(language, self._generic_extractor)

        symbols = extractor.extract_symbols(tree, source_code, file_path)
        edges = extractor.extract_edges(tree, source_code, file_path, symbols)
        diags = extractor.extract_diagnostics(tree, source_code, file_path)
        return symbols, edges, diags

    def supported_languages(self) -> list[str]:
        return list(self._extractors.keys())

    def register_extractor(self, language: str, extractor: LanguageExtractor) -> None:
        self._extractors[language] = extractor
