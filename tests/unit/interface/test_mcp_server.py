"""Tests for the MCP server."""
import json

import pytest
from unittest.mock import MagicMock

from mcp.types import ListToolsRequest, ListResourcesRequest

from codegraph.interface.mcp.server import CodegraphServer


class TestCodegraphServer:
    def test_server_creation(self):
        server = CodegraphServer()
        assert server._server is not None

    @pytest.mark.asyncio
    async def test_list_tools_registered(self):
        server = CodegraphServer()
        handler = server._server.request_handlers[ListToolsRequest]
        result = await handler(
            ListToolsRequest(method="tools/list", params=None)
        )
        tools = result.root.tools
        assert len(tools) == 14
        names = [t.name for t in tools]
        assert "get_symbols" in names
        assert "get_symbol" in names
        assert "get_imports" in names
        assert "get_dependents" in names
        assert "get_call_graph" in names
        assert "get_hierarchy" in names
        assert "find_references" in names
        assert "resolve_symbol" in names
        assert "get_snippet" in names
        assert "get_diff" in names
        assert "get_changed_files" in names
        assert "semantic_search" in names
        assert "get_file_summary" in names
        assert "get_repo_overview" in names

    @pytest.mark.asyncio
    async def test_list_resources_registered(self):
        server = CodegraphServer()
        handler = server._server.request_handlers[ListResourcesRequest]
        result = await handler(
            ListResourcesRequest(method="resources/list", params=None)
        )
        resources = result.root.resources
        assert len(resources) == 2
        uris = [str(r.uri) for r in resources]
        assert "codegraph://status" in uris
        assert "codegraph://languages" in uris

    @pytest.mark.asyncio
    async def test_handle_get_repo_overview(self):
        store = MagicMock()
        store.get_metadata.return_value = None
        server = CodegraphServer(store=store)
        result = await server._handle_tool("get_repo_overview", {})
        assert "indexed" in result

    @pytest.mark.asyncio
    async def test_handle_unknown_tool(self):
        server = CodegraphServer()
        result = await server._handle_tool("nonexistent", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_handle_get_snippet(self, tmp_path):
        (tmp_path / "test.py").write_text("x = 1\ny = 2\n")
        server = CodegraphServer(repo_root=str(tmp_path))
        result = await server._handle_tool("get_snippet", {"file_path": "test.py"})
        assert "content" in result

    @pytest.mark.asyncio
    async def test_handle_get_symbols(self):
        store = MagicMock()
        store.query_symbols.return_value = ([], None)
        server = CodegraphServer(store=store)
        result = await server._handle_tool("get_symbols", {})
        assert "symbols" in result
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_handle_get_symbols_with_kind(self):
        store = MagicMock()
        store.query_symbols.return_value = ([], None)
        server = CodegraphServer(store=store)
        result = await server._handle_tool("get_symbols", {"kind": "function"})
        assert "symbols" in result
        # Verify SymbolKind enum was passed to store
        call_args = store.query_symbols.call_args
        from codegraph.domain.models import SymbolKind
        assert call_args.kwargs.get("kind") == SymbolKind.FUNCTION

    @pytest.mark.asyncio
    async def test_handle_get_dependents_strips_symbol_key(self):
        store = MagicMock()
        store.get_edges.return_value = ([], None)
        server = CodegraphServer(store=store)
        # symbol_key should be stripped since GetDependentsUseCase doesn't accept it
        result = await server._handle_tool(
            "get_dependents", {"symbol_id": "abc", "symbol_key": "mod.Foo"}
        )
        assert "dependents" in result

    @pytest.mark.asyncio
    async def test_handle_find_references_strips_symbol_key(self):
        store = MagicMock()
        store.get_edges.return_value = ([], None)
        server = CodegraphServer(store=store)
        result = await server._handle_tool(
            "find_references", {"symbol_id": "abc", "symbol_key": "mod.Foo"}
        )
        assert "references" in result

    def test_get_version(self):
        server = CodegraphServer()
        version = server._get_version()
        assert version == "0.1.0"

    def test_get_index_state_no_store(self):
        server = CodegraphServer(store=None)
        gen, stale = server._get_index_state()
        assert gen == 0
        assert stale is True

    def test_get_index_state_no_metadata(self):
        store = MagicMock()
        store.get_metadata.return_value = None
        server = CodegraphServer(store=store)
        gen, stale = server._get_index_state()
        assert gen == 0
        assert stale is True

    def test_get_index_state_with_metadata(self):
        store = MagicMock()
        metadata = MagicMock()
        metadata.generation = 5
        store.get_metadata.return_value = metadata
        server = CodegraphServer(store=store)
        gen, stale = server._get_index_state()
        assert gen == 5
        assert stale is False

    def test_tool_and_resource_handler_count(self):
        """Verify the right number of handlers are registered."""
        server = CodegraphServer()
        handlers = server._server.request_handlers
        assert ListToolsRequest in handlers
        assert ListResourcesRequest in handlers
