"""Structured MCP response types. All tool responses use these."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 1

# NOTE: server_version should be injected from the interface layer, e.g.:
#   from importlib.metadata import version as pkg_version
#   server_version = pkg_version("codegraph-mcp")


@dataclass
class McpMeta:
    server_version: str
    request_id: str
    generation: int
    stale: bool
    duration_ms: int
    session_tokens_saved: int = 0

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "server_version": self.server_version,
            "request_id": self.request_id,
            "generation": self.generation,
            "stale": self.stale,
            "duration_ms": self.duration_ms,
            "session_tokens_saved": self.session_tokens_saved,
        }


@dataclass
class ToolResponse:
    meta: McpMeta
    data: dict

    def to_dict(self) -> dict:
        result = {"_meta": self.meta.to_dict()}
        result.update(self.data)
        return result


@dataclass
class ErrorResponse:
    error: str
    message: str
    details: Optional[dict] = None

    def to_dict(self) -> dict:
        d = {"error": self.error, "message": self.message}
        if self.details:
            d["details"] = self.details
        return d


@dataclass
class PaginatedResponse:
    meta: McpMeta
    data: dict
    total_count: int
    returned_count: int
    next_cursor: Optional[str] = None

    def to_dict(self) -> dict:
        result = {"_meta": self.meta.to_dict()}
        result.update(self.data)
        result["total_count"] = self.total_count
        result["returned_count"] = self.returned_count
        if self.next_cursor:
            result["next_cursor"] = self.next_cursor
        return result
