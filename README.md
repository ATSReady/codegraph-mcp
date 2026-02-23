# codegraph-mcp

MCP server that gives AI coding agents structural and semantic understanding of any codebase. Parses code with tree-sitter, stores symbols/edges/chunks in LanceDB, and exposes 16 tools + 4 resources over the Model Context Protocol.

## Features

- **Language-agnostic parsing** via tree-sitter (Python, TypeScript, JavaScript, Go, Rust, Java, and more)
- **Code graph** — symbols, call graphs, import chains, inheritance hierarchies, cross-file references
- **Semantic search** — vector embeddings with local ONNX, OpenAI, or Voyage providers
- **Incremental reindex** — only re-parses changed files
- **MCP protocol** — works with any MCP-compatible AI client

## Quick Install

```bash
git clone https://github.com/your-org/codegraph-mcp.git
cd codegraph-mcp
./install.sh
```

This will:
1. Install `codegraph` globally (via pipx, uv, or pip)
2. Register it as an MCP server in **Claude Code**, **Codex CLI**, **Gemini CLI**, and **OpenCode**
3. Set MCP startup timeout to **30 seconds**

You can also run the installer from the CLI after package install:

```bash
codegraph install
```

## Manual Install

### 1. Install the package

**With pipx (recommended):**

```bash
pipx install /path/to/codegraph-mcp
```

**With uv:**

```bash
uv tool install /path/to/codegraph-mcp
```

**With pip:**

```bash
pip install --user /path/to/codegraph-mcp
```

**From source (development):**

```bash
pip install -e ".[dev]"
```

### 2. Configure AI clients (global, recommended)

```bash
codegraph install --timeout-sec 30
```

#### Claude Code

```bash
claude mcp add --scope user codegraph -- codegraph serve
```

Or add manually to `~/.claude.json`:

```json
{
  "mcpServers": {
    "codegraph": {
      "type": "stdio",
      "command": "codegraph",
      "args": ["serve"]
    }
  }
}
```

#### Codex CLI

```bash
codex mcp add codegraph -- codegraph serve
```

Or add to `~/.codex/config.toml`:

```toml
[mcp_servers.codegraph]
command = "codegraph"
args = ["serve"]
startup_timeout_sec = 30
```

#### Gemini CLI

```bash
gemini mcp add codegraph -- codegraph serve
```

Or add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "codegraph",
      "args": ["serve"],
      "startup_timeout_sec": 30
    }
  }
}
```

#### OpenCode

Add to `~/.config/opencode/opencode.json`:

```json
{
  "mcp": {
    "codegraph": {
      "type": "local",
      "command": ["codegraph", "serve"],
      "startup_timeout_sec": 30
    }
  }
}
```

#### Per-project configuration

For project-scoped setup (shared with your team), create `.mcp.json` at the project root:

```json
{
  "mcpServers": {
    "codegraph": {
      "command": "codegraph",
      "args": ["serve", "--repo-root", "."]
    }
  }
}
```

This works with Claude Code and Gemini CLI. For Codex, use `.codex/config.toml` in the project root instead.

## Usage

### Index a repository

```bash
cd /path/to/your/repo
codegraph init          # creates .codegraph/ config
codegraph index         # builds the full code graph
```

`codegraph index` is incremental by default and only reindexes changed files.

### Live progress

```bash
codegraph index --progress
codegraph progress
codegraph progress --json
codegraph progress --watch --interval-ms 200
```

### Check status

```bash
codegraph status        # shows index state
codegraph status --json # machine-readable output
codegraph doctor        # health checks
```

### Start the MCP server manually

```bash
codegraph serve                          # current directory
codegraph serve --repo-root /path/to/repo  # specific repo
codegraph serve --log-level debug        # verbose logging
```

The server uses stdio transport. AI clients start it automatically — you normally don't need to run this yourself.

### List supported languages

```bash
codegraph languages
codegraph languages --json
```

## MCP Tools

The server exposes these tools to AI agents:

| Tool | Description |
|------|-------------|
| `get_symbols` | Query symbols by file, kind, name pattern |
| `get_symbol` | Get a single symbol by ID or key |
| `get_imports` | Get import edges for a file or symbol |
| `get_dependents` | Find what depends on a symbol |
| `get_call_graph` | Outgoing/incoming call edges |
| `get_hierarchy` | Class inheritance and interface implementations |
| `find_references` | All references to a symbol across the codebase |
| `resolve_symbol` | Fuzzy resolve a symbol name to candidates |
| `get_snippet` | Get source code for a file/line range |
| `get_diff` | Git diff between refs |
| `get_changed_files` | Files changed since a ref |
| `semantic_search` | Vector similarity search over code chunks |
| `get_file_summary` | Symbols and structure of a single file |
| `get_repo_overview` | High-level stats and file breakdown |
| `get_session_metrics` | Session token savings metrics |
| `get_index_progress` | Active/latest index or reindex progress snapshot |

## MCP Resources

| Resource | Description |
|----------|-------------|
| `codegraph://status` | Index generation, staleness, version |
| `codegraph://languages` | Supported languages and extensions |
| `codegraph://metrics` | Session token-savings metrics |
| `codegraph://index-progress` | Active/latest progress JSON payload |

## Configuration

Config lives in `.codegraph/config.toml`:

```toml
[index]
exclude = ["vendor/**", "generated/**", "**/*.min.js", "node_modules/**"]
parallel_workers = 1
partition_strategy = "hybrid"
min_partition_files = 1
progress_event_interval_ms = 250

[server]
auto_reindex = true
log_level = "info"

[embedding]
provider = "local"  # "local", "openai", or "voyage"
# api_key = "..."   # required for openai/voyage
# model = "..."     # optional model override
```

## Requirements

- Python 3.11+
- Git (for repository analysis)

## Development

```bash
git clone https://github.com/your-org/codegraph-mcp.git
cd codegraph-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT
