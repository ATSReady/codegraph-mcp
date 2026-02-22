"""MCP server for codegraph."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, Resource

from codegraph.domain.config import CodegraphConfig
from codegraph.domain.models import SymbolKind
from codegraph.interface.mcp.responses import ToolResponse, McpMeta, SCHEMA_VERSION


logger = logging.getLogger("codegraph.mcp")


class CodegraphServer:
    """MCP server exposing code graph tools and resources."""

    def __init__(
        self,
        store=None,
        parser=None,
        git_client=None,
        embedding_provider=None,
        chunker=None,
        config: Optional[CodegraphConfig] = None,
        repo_root: str = ".",
    ) -> None:
        self._store = store
        self._parser = parser
        self._git = git_client
        self._embedder = embedding_provider
        self._chunker = chunker
        self._config = config or CodegraphConfig()
        self._repo_root = repo_root
        self._server = Server("codegraph")
        self._setup_tools()
        self._setup_resources()

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _setup_tools(self) -> None:
        """Register all tool handlers."""
        server = self._server

        @server.list_tools()
        async def list_tools():
            return [
                Tool(
                    name="get_symbols",
                    description="Query symbols with filtering by file, kind, and name pattern",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "kind": {"type": "string"},
                            "name_pattern": {"type": "string"},
                            "max_results": {"type": "integer", "default": 50},
                            "cursor": {"type": "string"},
                        },
                    },
                ),
                Tool(
                    name="get_symbol",
                    description="Get a single symbol by ID or key",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol_id": {"type": "string"},
                            "symbol_key": {"type": "string"},
                        },
                    },
                ),
                Tool(
                    name="get_imports",
                    description="Get import edges for a file or symbol",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "symbol_id": {"type": "string"},
                        },
                    },
                ),
                Tool(
                    name="get_dependents",
                    description="Find what depends on a symbol",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol_id": {"type": "string"},
                            "symbol_key": {"type": "string"},
                        },
                    },
                ),
                Tool(
                    name="get_call_graph",
                    description="Get call edges from/to a symbol",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol_id": {
                                "type": "string",
                                "description": "Required",
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["outgoing", "incoming"],
                                "default": "outgoing",
                            },
                        },
                        "required": ["symbol_id"],
                    },
                ),
                Tool(
                    name="get_hierarchy",
                    description="Get inheritance hierarchy",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol_id": {
                                "type": "string",
                                "description": "Required",
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["ancestors", "descendants"],
                                "default": "ancestors",
                            },
                        },
                        "required": ["symbol_id"],
                    },
                ),
                Tool(
                    name="find_references",
                    description="Find all references to a symbol",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol_id": {"type": "string"},
                            "symbol_key": {"type": "string"},
                        },
                    },
                ),
                Tool(
                    name="resolve_symbol",
                    description="Resolve a symbol name to candidates",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Required",
                            },
                            "kind": {"type": "string"},
                            "file_context": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                ),
                Tool(
                    name="get_snippet",
                    description="Get source code snippet",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Required",
                            },
                            "start_line": {"type": "integer", "default": 1},
                            "end_line": {"type": "integer", "default": 0},
                            "max_lines": {"type": "integer", "default": 120},
                        },
                        "required": ["file_path"],
                    },
                ),
                Tool(
                    name="get_diff",
                    description="Get unified diff for a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Required",
                            },
                            "base_ref": {"type": "string"},
                            "head_ref": {"type": "string"},
                            "context_lines": {"type": "integer", "default": 3},
                        },
                        "required": ["file_path"],
                    },
                ),
                Tool(
                    name="get_changed_files",
                    description="List changed files",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "base_ref": {"type": "string"},
                            "head_ref": {
                                "type": "string",
                                "default": "HEAD",
                            },
                            "include_worktree": {
                                "type": "boolean",
                                "default": True,
                            },
                        },
                    },
                ),
                Tool(
                    name="semantic_search",
                    description="Search code semantically using embeddings",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Required",
                            },
                            "max_results": {"type": "integer", "default": 10},
                            "file_filter": {"type": "string"},
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="get_file_summary",
                    description="Get structural summary of a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Required",
                            },
                        },
                        "required": ["file_path"],
                    },
                ),
                Tool(
                    name="get_repo_overview",
                    description="Get repository index overview",
                    inputSchema={"type": "object", "properties": {}},
                ),
            ]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict):
            request_id = str(uuid.uuid4())[:8]
            start = time.time()
            try:
                result = await self._handle_tool(name, arguments)
                duration = time.time() - start
                generation, stale = self._get_index_state()
                meta = McpMeta(
                    server_version=self._get_version(),
                    request_id=request_id,
                    generation=generation,
                    stale=stale,
                    duration_ms=round(duration * 1000),
                )
                response = ToolResponse(data=result, meta=meta)
                return [TextContent(type="text", text=json.dumps(response.to_dict()))]
            except Exception as e:
                logger.exception("Tool %s failed: %s", name, e)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": str(e), "_meta": {"request_id": request_id}}
                        ),
                    )
                ]

    # ------------------------------------------------------------------
    # Tool routing
    # ------------------------------------------------------------------

    async def _handle_tool(self, name: str, args: dict) -> dict:
        """Route tool calls to use cases."""
        from codegraph.application.tools.get_symbols import GetSymbolsUseCase
        from codegraph.application.tools.get_symbol import GetSymbolUseCase
        from codegraph.application.tools.get_imports import GetImportsUseCase
        from codegraph.application.tools.get_dependents import GetDependentsUseCase
        from codegraph.application.tools.get_call_graph import GetCallGraphUseCase
        from codegraph.application.tools.get_hierarchy import GetHierarchyUseCase
        from codegraph.application.tools.find_references import FindReferencesUseCase
        from codegraph.application.tools.resolve_symbol import ResolveSymbolUseCase
        from codegraph.application.tools.get_snippet import GetSnippetUseCase
        from codegraph.application.tools.get_diff import GetDiffUseCase
        from codegraph.application.tools.get_changed_files import GetChangedFilesUseCase
        from codegraph.application.tools.semantic_search import SemanticSearchUseCase
        from codegraph.application.tools.get_file_summary import GetFileSummaryUseCase
        from codegraph.application.tools.get_repo_overview import GetRepoOverviewUseCase

        # Coerce string 'kind' to SymbolKind enum where needed
        coerced = dict(args)
        if "kind" in coerced and coerced["kind"] is not None:
            try:
                coerced["kind"] = SymbolKind(coerced["kind"])
            except ValueError:
                pass  # let use case handle invalid kind

        # Some tool schemas expose symbol_key but the underlying use case
        # only accepts symbol_id.  Strip unsupported kwargs before dispatch.
        id_only = {k: v for k, v in coerced.items() if k != "symbol_key"}

        handlers = {
            "get_symbols": lambda: GetSymbolsUseCase(self._store).execute(**coerced),
            "get_symbol": lambda: GetSymbolUseCase(self._store).execute(**coerced),
            "get_imports": lambda: GetImportsUseCase(self._store).execute(**coerced),
            "get_dependents": lambda: GetDependentsUseCase(self._store).execute(**id_only),
            "get_call_graph": lambda: GetCallGraphUseCase(self._store).execute(**coerced),
            "get_hierarchy": lambda: GetHierarchyUseCase(self._store).execute(**coerced),
            "find_references": lambda: FindReferencesUseCase(self._store).execute(**id_only),
            "resolve_symbol": lambda: ResolveSymbolUseCase(self._store).execute(**coerced),
            "get_snippet": lambda: GetSnippetUseCase(self._repo_root).execute(**coerced),
            "get_diff": lambda: GetDiffUseCase(self._git).execute(**coerced),
            "get_changed_files": lambda: GetChangedFilesUseCase(self._git).execute(**coerced),
            "semantic_search": lambda: SemanticSearchUseCase(
                self._store, self._embedder
            ).execute(**coerced),
            "get_file_summary": lambda: GetFileSummaryUseCase(self._store).execute(**coerced),
            "get_repo_overview": lambda: GetRepoOverviewUseCase(
                self._store, self._git
            ).execute(),
        }

        handler = handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}

        result = handler()
        if asyncio.iscoroutine(result):
            result = await result
        return result

    # ------------------------------------------------------------------
    # Resource registration
    # ------------------------------------------------------------------

    def _setup_resources(self) -> None:
        """Register resource handlers."""
        server = self._server

        @server.list_resources()
        async def list_resources():
            return [
                Resource(
                    uri="codegraph://status",
                    name="Index Status",
                    description="Current index status and health",
                ),
                Resource(
                    uri="codegraph://languages",
                    name="Supported Languages",
                    description="List of supported programming languages",
                ),
            ]

        @server.read_resource()
        async def read_resource(uri):
            uri_str = str(uri)
            if uri_str == "codegraph://status":
                from codegraph.application.tools.get_repo_overview import (
                    GetRepoOverviewUseCase,
                )

                data = GetRepoOverviewUseCase(self._store, self._git).execute()
                return json.dumps(data)
            elif uri_str == "codegraph://languages":
                from codegraph.infrastructure.parsers.languages import (
                    available_languages,
                )

                return json.dumps({"languages": available_languages()})
            return json.dumps({"error": f"Unknown resource: {uri_str}"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_index_state(self) -> tuple[int, bool]:
        """Return (generation, stale) from stored metadata."""
        if self._store is None:
            return 0, True
        try:
            metadata = self._store.get_metadata()
            if metadata is None:
                return 0, True
            stale = False
            if self._git:
                from codegraph.application.staleness import StalenessChecker

                result = StalenessChecker(self._store, self._git).check()
                stale = result.is_stale
            return metadata.generation, stale
        except Exception:
            return 0, True

    def _get_version(self) -> str:
        try:
            from importlib.metadata import version

            return version("codegraph-mcp")
        except Exception:
            return "0.1.0"

    async def run(self) -> None:
        """Run the MCP server with stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream,
                write_stream,
                self._server.create_initialization_options(),
            )
