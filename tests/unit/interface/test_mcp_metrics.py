"""Tests for metrics integration in MCP server."""
import asyncio

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


class TestGetSessionMetricsTool:
    def test_handle_tool_returns_metrics(self):
        """get_session_metrics should return metrics dict via _handle_tool."""
        from codegraph.interface.mcp.server import CodegraphServer

        server = CodegraphServer()
        # Record some metrics to verify they show up
        server._metrics.record("get_snippet", naive_tokens=5000, actual_tokens=800)

        result = asyncio.get_event_loop().run_until_complete(
            server._handle_tool("get_session_metrics", {})
        )
        assert "tools" in result
        assert "total_saved" in result
        assert "formatted" in result
        assert result["total_saved"] == 4200
        assert len(result["tools"]) == 1
        assert result["tools"][0]["tool"] == "get_snippet"
