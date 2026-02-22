"""Tests for metrics integration in MCP server."""
import pytest

from codegraph.interface.mcp.responses import McpMeta


class TestMcpMetaSessionTokens:
    def test_includes_session_tokens_saved(self):
        meta = McpMeta(
            server_version="0.1.0",
            request_id="abc123",
            generation=1,
            stale=False,
            duration_ms=42,
            session_tokens_saved=5000,
        )
        d = meta.to_dict()
        assert d["session_tokens_saved"] == 5000

    def test_defaults_to_zero(self):
        meta = McpMeta(
            server_version="0.1.0",
            request_id="abc123",
            generation=1,
            stale=False,
            duration_ms=42,
        )
        d = meta.to_dict()
        assert d["session_tokens_saved"] == 0
