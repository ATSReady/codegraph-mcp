# codegraph-mcp

## Project Structure (Clean Architecture)

- `src/codegraph/domain/` — Pure types, no IO. Symbol, Edge, Chunk, WorkspaceState, etc.
- `src/codegraph/application/` — Use-cases. IndexRepo, SemanticSearch, GetDependents, etc.
- `src/codegraph/infrastructure/` — Adapters. Tree-sitter, LanceDB, Git, Embeddings, Watchers.
- `src/codegraph/interface/` — CLI (Click) and MCP server endpoints.
- `tests/unit/` — Unit tests per layer.
- `tests/integration/` — End-to-end tests.

## Commands

- `pytest` — Run all tests
- `pytest tests/unit/` — Unit tests only
- `codegraph index` — Full index
- `codegraph serve` — Start MCP server
- `codegraph status` — Show index health
- `codegraph doctor` — Health check

## Architecture Rules

- Domain MUST NOT import infrastructure.
- Use Protocol for ports (interfaces).
- No global state, no singletons.
- All tool responses are structured JSON with `_meta` block.
