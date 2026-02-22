# src/codegraph/domain/models.py
"""Core domain models for codegraph. Pure data, no IO."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SymbolKind(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    TYPE = "type"
    VARIABLE = "variable"
    IMPORT = "import"
    MODULE = "module"
    TYPE_ALIAS = "type_alias"
    ENUM = "enum"


class EdgeKind(str, Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    TYPE_REF = "type_ref"
    READ = "read"
    WRITE = "write"


class ReferenceKind(str, Enum):
    IMPORT = "import"
    CALL = "call"
    READ = "read"
    WRITE = "write"
    TYPE = "type"
    INHERIT = "inherit"
    STRING = "string"
    COMMENT = "comment"


def _normalize_signature(sig: str) -> str:
    """Normalize a signature for hashing.

    Preserves parameter order. Normalizes whitespace only.
    Does NOT reorder anything that changes semantics.
    """
    normalized = re.sub(r"\s+", " ", sig.strip())
    # Remove spaces around parentheses and after commas for stability
    normalized = re.sub(r"\s*\(\s*", "(", normalized)
    normalized = re.sub(r"\s*\)\s*", ")", normalized)
    normalized = re.sub(r"\s*,\s*", ", ", normalized)
    return normalized


def _hash8(text: str) -> str:
    """First 8 chars of SHA-256 hex digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _hash_full(text: str) -> str:
    """Full SHA-256 hex digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    signature: str
    language: str
    module_path: str = ""
    container_symbol_id: Optional[str] = None
    container_name: Optional[str] = None
    docstring: Optional[str] = None
    index_generation: int = 0
    indexed_at: Optional[str] = None

    @property
    def symbol_id(self) -> str:
        return f"{self.file_path}:{self.name}:{self.kind.value}:{self.start_line}"

    @property
    def symbol_key(self) -> str:
        prefix = self.module_path if self.module_path else self._file_path_to_module()
        if self.container_name:
            return f"{prefix}.{self.container_name}.{self.name}:{self.kind.value}"
        return f"{prefix}.{self.name}:{self.kind.value}"

    def _file_path_to_module(self) -> str:
        """Convert file_path to module-like format: src/auth/middleware.py -> src.auth.middleware"""
        path = self.file_path
        for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".cs", ".go", ".rs", ".c", ".cpp", ".h", ".hpp"):
            if path.endswith(ext):
                path = path[: -len(ext)]
                break
        return path.replace("/", ".").replace("\\", ".")

    @property
    def symbol_key_exact(self) -> str:
        sig_hash = _hash8(_normalize_signature(self.signature))
        return f"{self.symbol_key}:{sig_hash}"

    def to_dict(self) -> dict:
        return {
            "symbol_id": self.symbol_id,
            "symbol_key": self.symbol_key,
            "symbol_key_exact": self.symbol_key_exact,
            "container_symbol_id": self.container_symbol_id,
            "name": self.name,
            "kind": self.kind.value,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signature": self.signature,
            "docstring": self.docstring,
            "language": self.language,
        }


@dataclass(frozen=True)
class Edge:
    source_symbol_id: str
    kind: EdgeKind
    file_path: str
    start_line: int
    end_line: int
    column: int
    ref_text: str
    target_symbol_id: Optional[str] = None
    resolution_confidence: float = 0.0
    resolution_method: Optional[str] = None
    resolver_id: Optional[str] = None
    resolved_at_generation: Optional[int] = None
    index_generation: int = 0
    indexed_at: Optional[str] = None

    @property
    def edge_id(self) -> str:
        """Stable identity excluding target (which is mutable)."""
        payload = (
            f"{self.kind.value}|{self.file_path}|{self.start_line}|"
            f"{self.column}|{self.ref_text}|{self.source_symbol_id}"
        )
        return _hash_full(payload)

    @property
    def edge_id8(self) -> str:
        return self.edge_id[:8]


def _normalize_content(content: str) -> str:
    """Normalize content for hashing: normalize line endings and strip trailing whitespace per line."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.splitlines())


@dataclass
class Chunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol_ids: list[str]
    is_symbol_chunk: bool
    symbol_key_exact: Optional[str] = None
    language: Optional[str] = None
    vector: Optional[list[float]] = None
    has_vector: bool = False
    embedded_hash8: Optional[str] = None
    vector_updated_at: Optional[str] = None
    was_truncated: bool = False
    index_generation: int = 0
    indexed_at: Optional[str] = None

    @property
    def content_hash(self) -> str:
        return _hash_full(_normalize_content(self.content))

    @property
    def content_hash8(self) -> str:
        return _hash8(_normalize_content(self.content))

    @property
    def content_length_chars(self) -> int:
        return len(self.content)

    @property
    def content_lines(self) -> int:
        return len(self.content.splitlines())

    @property
    def chunk_id(self) -> str:
        if self.is_symbol_chunk and self.symbol_key_exact:
            return self.symbol_key_exact
        return f"{self.file_path}:window:{self.start_line}:{self.content_hash8}"
