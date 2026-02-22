"""Base extractor protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codegraph.domain.models import Symbol, Edge
from codegraph.domain.workspace import FileDiagnostic


class LanguageExtractor(ABC):
    """Base class for language-specific symbol/edge extractors."""

    @abstractmethod
    def extract_symbols(self, tree: object, source_code: str, file_path: str) -> list[Symbol]:
        ...

    @abstractmethod
    def extract_edges(
        self, tree: object, source_code: str, file_path: str, symbols: list[Symbol],
    ) -> list[Edge]:
        ...

    @abstractmethod
    def extract_diagnostics(
        self, tree: object, source_code: str, file_path: str,
    ) -> list[FileDiagnostic]:
        ...
