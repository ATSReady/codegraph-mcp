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

        result = asyncio.run(server._handle_tool("get_session_metrics", {}))
        assert "tools" in result
        assert "total_saved" in result
        assert "formatted" in result
        assert result["total_saved"] == 4200
        assert len(result["tools"]) == 1
        assert result["tools"][0]["tool"] == "get_snippet"


class TestInlineSavingsHint:
    def test_hint_format_over_1k(self):
        saved = 5200
        saved_str = f"~{saved / 1000:.1f}k" if saved >= 1000 else f"~{saved}"
        hint = f"[codegraph: {saved_str} tokens saved this session]"
        assert hint == "[codegraph: ~5.2k tokens saved this session]"

    def test_hint_format_under_1k(self):
        saved = 800
        saved_str = f"~{saved / 1000:.1f}k" if saved >= 1000 else f"~{saved}"
        hint = f"[codegraph: {saved_str} tokens saved this session]"
        assert hint == "[codegraph: ~800 tokens saved this session]"
