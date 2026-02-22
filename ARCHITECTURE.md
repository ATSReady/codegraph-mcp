# Architecture

## Overview

codegraph-mcp is an MCP (Model Context Protocol) server that builds a structural and semantic code graph from a repository. It parses source files using tree-sitter, stores symbols/edges/chunks in LanceDB, optionally embeds code for vector search, and exposes the graph through MCP tools and a CLI.

The codebase follows Clean Architecture with strict dependency direction: domain has zero external dependencies, application orchestrates domain types through port interfaces, infrastructure implements those ports, and interface wires everything together.

## Architecture Layers

Dependencies point inward only. Nothing in the inner rings imports from outer rings.

```
  +------------------------------------------------------+
  |  Interface  (MCP server, CLI)                        |
  |  +------------------------------------------------+  |
  |  |  Infrastructure  (tree-sitter, LanceDB, git)   |  |
  |  |  +------------------------------------------+  |  |
  |  |  |  Application  (use cases, tools)         |  |  |
  |  |  |  +------------------------------------+  |  |  |
  |  |  |  |  Domain  (models, ports, config)   |  |  |  |
  |  |  |  +------------------------------------+  |  |  |
  |  |  +------------------------------------------+  |  |
  |  +------------------------------------------------+  |
  +------------------------------------------------------+
```

- **Domain** depends on nothing (stdlib only).
- **Application** depends on Domain.
- **Infrastructure** depends on Domain (implements port protocols).
- **Interface** depends on Application and Infrastructure (wires adapters to use cases).

## Module Structure

```
src/codegraph/
|-- domain/
|   |-- models.py          # Symbol, Edge, Chunk, SymbolKind, EdgeKind
|   |-- ports.py           # Protocol interfaces (SymbolStore, EmbeddingProvider, etc.)
|   |-- workspace.py       # WorkspaceState, IndexMetadata, FileDiagnostic
|   |-- config.py          # CodegraphConfig, IndexConfig, EmbeddingConfig, etc.
|   |-- errors.py          # Typed error hierarchy (CodegraphError subclasses)
|
|-- application/
|   |-- index_repo.py      # IndexRepoUseCase — full repository indexing
|   |-- reindex.py          # IncrementalReindexUseCase — changed-files-only reindex
|   |-- staleness.py        # StalenessChecker, ReindexGuard (single-flight)
|   |-- tools/
|       |-- get_symbol.py        # GetSymbolUseCase
|       |-- get_symbols.py       # GetSymbolsUseCase (query with filters)
|       |-- find_references.py   # FindReferencesUseCase
|       |-- get_call_graph.py    # GetCallGraphUseCase
|       |-- get_dependents.py    # GetDependentsUseCase
|       |-- get_hierarchy.py     # GetHierarchyUseCase
|       |-- get_imports.py       # GetImportsUseCase
|       |-- get_file_summary.py  # GetFileSummaryUseCase
|       |-- get_repo_overview.py # GetRepoOverviewUseCase
|       |-- get_snippet.py       # GetSnippetUseCase
|       |-- get_diff.py          # GetDiffUseCase
|       |-- get_changed_files.py # GetChangedFilesUseCase
|       |-- resolve_symbol.py    # ResolveSymbolUseCase
|       |-- semantic_search.py   # SemanticSearchUseCase
|
|-- infrastructure/
|   |-- parsers/
|   |   |-- languages.py             # Language detection, grammar loading
|   |   |-- tree_sitter_parser.py    # TreeSitterParser (CodeParser adapter)
|   |   |-- chunker.py               # CodeChunker — symbol-aware file chunking
|   |   |-- extractors/
|   |   |   |-- base.py              # LanguageExtractor ABC
|   |   |   |-- python_extractor.py  # PythonExtractor
|   |   |   |-- typescript_extractor.py  # TypeScriptExtractor (handles .ts/.tsx)
|   |   |   |-- javascript_extractor.py  # JavaScriptExtractor (handles .js/.jsx)
|   |   |   |-- generic_extractor.py     # GenericExtractor (fallback)
|   |   |-- resolvers/
|   |       |-- python_resolver.py       # PythonImportResolver
|   |       |-- typescript_resolver.py   # TypeScriptImportResolver
|   |
|   |-- embeddings/
|   |   |-- base.py             # EmbeddingResult, normalize_l2, pack_batches
|   |   |-- factory.py          # EmbeddingProviderFactory
|   |   |-- local_onnx.py       # LocalOnnxProvider (nomic-embed-text-v1.5)
|   |   |-- openai_provider.py  # OpenAIProvider
|   |   |-- voyage_provider.py  # VoyageProvider
|   |
|   |-- storage/
|   |   |-- lancedb_store.py    # LanceDBStore (SymbolStore adapter)
|   |   |-- lock.py             # IndexLock (file-based locking)
|   |
|   |-- git/
|   |   |-- client.py           # SubprocessGitClient (GitClient adapter)
|   |
|   |-- watchers/
|   |   |-- git_watcher.py      # GitWatcher (polling-based file watcher)
|   |
|   |-- config_loader.py        # load_config(), _parse_config()
|   |-- logging_config.py       # setup_logging(), StructuredFormatter
|
|-- interface/
    |-- mcp/
    |   |-- server.py           # MCP server (tool registration, request handling)
    |   |-- responses.py        # McpMeta, ToolResponse, ErrorResponse, PaginatedResponse
    |
    |-- cli/
        |-- main.py             # Click CLI group, init command, entry point
        |-- index_cmd.py        # `codegraph index` command
        |-- status_cmd.py       # `codegraph status` and `codegraph doctor` commands
```

## Domain Layer

The domain contains pure data types with no IO, no framework imports, and no infrastructure dependencies. Everything is defined using `dataclasses` and `enum`.

### Core Types

**`Symbol`** (frozen dataclass) represents a named code entity:

```python
@dataclass(frozen=True)
class Symbol:
    name: str
    kind: SymbolKind           # function, method, class, interface, type, variable, import, module, enum
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
```

**`Edge`** (frozen dataclass) represents a relationship between symbols:

```python
@dataclass(frozen=True)
class Edge:
    source_symbol_id: str
    kind: EdgeKind             # imports, calls, inherits, implements, type_ref, read, write
    file_path: str
    start_line: int
    end_line: int
    column: int
    ref_text: str
    target_symbol_id: Optional[str] = None     # mutable via resolution
    resolution_confidence: float = 0.0
```

**`Chunk`** (mutable dataclass) represents an embeddable code segment:

```python
@dataclass
class Chunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbol_ids: list[str]
    is_symbol_chunk: bool
    vector: Optional[list[float]] = None       # populated by embedding provider
    has_vector: bool = False
```

### Dual-Key Identity

Symbols have three identity levels:

| Property | Format | Purpose |
|---|---|---|
| `symbol_id` | `file:name:kind:line` | Position-based, unique within an index |
| `symbol_key` | `module.Container.name:kind` | Semantic, stable across refactors within a module |
| `symbol_key_exact` | `symbol_key:sig_hash8` | Signature-sensitive, detects API changes |

Edges use a content-hash `edge_id` derived from `kind|file|line|column|ref_text|source_symbol_id` to maintain identity independent of the (mutable) target.

Chunks use `symbol_key_exact` for symbol chunks or `file:window:line:content_hash8` for gap chunks.

### Port Protocols

All infrastructure interfaces are defined as `@runtime_checkable` Protocol classes in `domain/ports.py`:

| Protocol | Purpose | Key Methods |
|---|---|---|
| `SymbolStore` | Persistence for symbols, edges, chunks, metadata | `get_symbol`, `upsert_symbols`, `vector_search`, `get_metadata` |
| `EmbeddingProvider` | Text-to-vector embedding | `embed_batch`, `embed_single`, `estimate_tokens` |
| `GitClient` | Git repository operations | `get_head_commit`, `get_changed_files_since`, `is_dirty` |
| `CodeParser` | Source file parsing | `parse_file`, `detect_language`, `available_languages` |
| `ImportResolver` | Cross-file import resolution | `resolve_imports` |
| `FileWatcher` | Filesystem change detection | `start`, `stop`, `is_available` |

### Error Hierarchy

All errors extend `CodegraphError` with a stable `error_code` string:

- `NoIndexError` (`no_index`) — no index exists yet
- `ProviderUnavailableError` (`provider_unavailable`) — embedding provider not available
- `ProviderMismatchError` (`provider_mismatch`) — configured vs. indexed provider differ
- `IndexLockedError` (`index_locked`) — another process holds the lock
- `InvalidArgsError` (`invalid_args`) — bad tool arguments
- `BlockedError` (`blocked`) — operation blocked by another

Each error has a `to_dict()` method for structured MCP error responses.

## Application Layer

The application layer contains use cases that orchestrate domain types through port interfaces. Use cases accept port implementations via constructor injection.

### Indexing Use Cases

**`IndexRepoUseCase`** — full repository indexing pipeline:

1. Discover files (walk directory, filter by language support and exclude patterns)
2. Determine generation number (increment from metadata)
3. Parse each file via `CodeParser` port, stamp generation on symbols/edges
4. Chunk files via `CodeChunker` (symbol-aware chunking)
5. Embed chunks via `EmbeddingProvider` port (if available)
6. Write symbols, edges, chunks to `SymbolStore` port
7. Build and store `IndexMetadata` with `WorkspaceState`

**`IncrementalReindexUseCase`** — delta reindex:

1. Read stored metadata to get last indexed commit
2. Query `GitClient` for changed files since that commit
3. Delete old data for changed/deleted files
4. Re-parse and re-embed only affected files
5. Update metadata with new generation and HEAD commit

### Staleness and Reindex Guard

**`StalenessChecker`** compares stored `IndexMetadata` against current repo state. Returns a `StalenessResult` with `is_stale`, `reason` (`no_index`, `head_changed`, `worktree_dirty`), and `changed_file_count`.

**`ReindexGuard`** implements single-flight coalescing with a threading lock. If a reindex is already running, subsequent requests set a `_pending` flag rather than running concurrently. `should_block()` decides whether a caller should wait for an inline reindex based on staleness severity (`max_files` threshold).

### Tool Use Cases

Each tool in `application/tools/` follows the same pattern: a class with `__init__(self, store, ...)` accepting port implementations, and an `execute(...)` method returning a dict. Examples:

- `GetSymbolUseCase` — lookup by `symbol_id` or `symbol_key`
- `SemanticSearchUseCase` — embed query text, run `vector_search` on store
- `GetCallGraphUseCase` — traverse edges of kind `calls`
- `FindReferencesUseCase` — find edges targeting a symbol
- `GetDependentsUseCase` — reverse dependency traversal
- `GetHierarchyUseCase` — class inheritance traversal
- `GetImportsUseCase` — import edge listing
- `GetFileSummaryUseCase` — symbols and diagnostics for a file
- `GetRepoOverviewUseCase` — index-wide statistics
- `GetDiffUseCase` — unified diff via `GitClient`
- `GetChangedFilesUseCase` — changed files via `GitClient`

## Infrastructure Layer

Infrastructure implements domain port protocols using concrete libraries and external systems.

### Tree-sitter Parser

`TreeSitterParser` implements the `CodeParser` protocol. It uses the Strategy pattern for language-specific extraction:

```python
class TreeSitterParser:
    def __init__(self) -> None:
        self._extractors: dict[str, LanguageExtractor] = {
            "python": PythonExtractor(),
            "typescript": TypeScriptExtractor(),
            "tsx": TypeScriptExtractor(),
            "javascript": JavaScriptExtractor(),
            "jsx": JavaScriptExtractor(),
        }
        self._generic_extractor = GenericExtractor()

    def register_extractor(self, language: str, extractor: LanguageExtractor) -> None:
        self._extractors[language] = extractor
```

Each `LanguageExtractor` (ABC) implements three methods:
- `extract_symbols(tree, source_code, file_path) -> list[Symbol]`
- `extract_edges(tree, source_code, file_path, symbols) -> list[Edge]`
- `extract_diagnostics(tree, source_code, file_path) -> list[FileDiagnostic]`

Language detection is extension-based via `LANGUAGE_EXTENSIONS` in `languages.py`, supporting Python, TypeScript, TSX, JavaScript, JSX, Go, Rust, Java, C, C++, C#, Ruby, PHP, Swift, and Kotlin.

### Import Resolvers

`PythonImportResolver` resolves Python imports (relative and absolute) by detecting `__init__.py`-based package roots and searching the filesystem.

`TypeScriptImportResolver` resolves TypeScript/JavaScript imports, including `tsconfig.json` path aliases.

Both return `ResolvedImport` dataclasses with the resolved file path and confidence.

### Code Chunker

`CodeChunker` creates `Chunk` objects from source files. It produces two types:
- **Symbol chunks**: one chunk per symbol (function/class body), keyed by `symbol_key_exact`
- **Gap chunks**: sliding-window chunks for lines not covered by any symbol

Each chunk gets an `embedding_text` that includes metadata (file path, language, symbol info) prepended to the code content.

### LanceDB Store

`LanceDBStore` implements `SymbolStore`. It uses separate LanceDB tables for symbols, edges, chunks, metadata, and diagnostics. Key implementation details:

- Symbols, edges, and chunks are serialized to/from flat dictionaries for LanceDB rows
- Metadata is JSON-serialized into a single-row table
- Vector search uses LanceDB's native ANN search on the chunks table
- Cursor-based pagination uses base64-encoded offsets
- `compact()` delegates to LanceDB's compaction

### Index Lock

`IndexLock` provides file-based mutual exclusion using PID files. It writes `{pid}:{hostname}` to a lock file, supports context manager usage, and can break stale locks older than a configurable threshold (default 1 hour).

### Git Client

`SubprocessGitClient` implements `GitClient` by shelling out to `git` via `subprocess.run`. All git operations are synchronous. It handles diff parsing, status porcelain output, rename detection, and worktree dirty checks.

### Embedding Providers

Three providers implement the `EmbeddingProvider` protocol:

| Provider | Class | Default Model | Tokens | API |
|---|---|---|---|---|
| local | `LocalOnnxProvider` | nomic-embed-text-v1.5 | 8192 | ONNX Runtime (CPU) |
| openai | `OpenAIProvider` | text-embedding-3-small | 8191 | OpenAI REST API |
| voyage | `VoyageProvider` | voyage-code-2 | 16000 | Voyage AI REST API |

`EmbeddingProviderFactory` selects and instantiates a provider from `EmbeddingConfig`. The local ONNX provider uses lazy loading — the model and tokenizer are only initialized on first use.

API providers (`OpenAIProvider`, `VoyageProvider`) use `urllib` directly (no SDK dependency), support retry logic, and read API keys from environment variables.

Shared utilities in `base.py`:
- `normalize_l2()` — L2 vector normalization
- `pack_batches()` — bin-packing texts into batches respecting size and token limits
- `estimate_tokens()` — character-based token estimation heuristic

### File Watcher

`GitWatcher` uses a polling loop (threading-based) that monitors `.git/HEAD` and `.git/index` mtimes. When a change is detected, it fires a callback. This avoids a hard dependency on `watchdog` for basic change detection.

### Config Loading

`load_config()` reads `.codegraph/config.toml`, parses it into `CodegraphConfig`. Falls back to defaults when no config file exists. `save_default_config()` writes a starter config file.

### Logging

`setup_logging()` configures a `codegraph` logger with `StructuredFormatter` (JSON output) and `RotatingFileHandler`. `get_request_logger()` returns a `LoggerAdapter` with a `request_id` for per-request tracing.

## Interface Layer

### MCP Server

`server.py` creates an MCP server instance and registers tools as async handlers. Each handler:

1. Parses input arguments
2. Instantiates the appropriate use case with injected adapters
3. Calls `execute()` on the use case
4. Wraps the result in a `ToolResponse` with `McpMeta` (generation, staleness, duration)
5. Returns structured JSON

All responses include a `_meta` block with `schema_version`, `server_version`, `request_id`, `generation`, `stale`, and `duration_ms`.

### CLI

The CLI uses Click with a group structure:

- `codegraph init` — create `.codegraph/` directory and default config
- `codegraph index` — run `IndexRepoUseCase`
- `codegraph status` — show index health via `StalenessChecker`
- `codegraph doctor` — detailed health check

Entry point: `codegraph = "codegraph.interface.cli:main"` (registered in `pyproject.toml`).

## Design Patterns

| Pattern | Where | Purpose |
|---|---|---|
| **Strategy** | `LanguageExtractor` subclasses in `TreeSitterParser` | Language-specific parsing without conditional branching |
| **Factory** | `EmbeddingProviderFactory` | Select embedding provider from config string |
| **Adapter** | `LanceDBStore`, `SubprocessGitClient`, all providers | Wrap external libraries behind domain port protocols |
| **Command** | Each tool use case class | Encapsulate a query operation with its dependencies |
| **Single-flight** | `ReindexGuard` | Coalesce concurrent reindex requests into one execution |
| **Port/Adapter** | All `Protocol` classes in `ports.py` | Decouple domain logic from infrastructure implementations |
| **Lazy Loading** | `LocalOnnxProvider._ensure_loaded()` | Defer heavy model initialization until first use |

## Extending

### Adding a New Language Extractor

1. Create `src/codegraph/infrastructure/parsers/extractors/{language}_extractor.py`
2. Subclass `LanguageExtractor` and implement:

```python
from codegraph.infrastructure.parsers.extractors.base import LanguageExtractor
from codegraph.domain.models import Symbol, Edge, SymbolKind, EdgeKind
from codegraph.domain.workspace import FileDiagnostic

class GoExtractor(LanguageExtractor):
    def extract_symbols(self, tree, source_code: str, file_path: str) -> list[Symbol]:
        # Walk tree-sitter AST nodes, create Symbol for each function/type/etc.
        ...

    def extract_edges(self, tree, source_code: str, file_path: str, symbols: list[Symbol]) -> list[Edge]:
        # Walk AST for import statements, function calls, type references
        ...

    def extract_diagnostics(self, tree, source_code: str, file_path: str) -> list[FileDiagnostic]:
        # Collect ERROR nodes from tree-sitter parse tree
        ...
```

3. Register it in `TreeSitterParser.__init__()`:

```python
self._extractors["go"] = GoExtractor()
```

4. Ensure the language extension is in `LANGUAGE_EXTENSIONS` in `languages.py` (Go is already mapped: `".go": "go"`).

5. Optionally add an import resolver in `resolvers/` if the language has cross-file import semantics.

### Adding a New Embedding Provider

1. Create `src/codegraph/infrastructure/embeddings/{name}_provider.py`
2. Implement the `EmbeddingProvider` protocol attributes and methods:

```python
class MyProvider:
    """Implements EmbeddingProvider protocol."""

    def __init__(self, model: str, api_key: str, dimension: int, ...):
        self.name = "my_provider"
        self.dimension = dimension
        self.max_tokens = 8192
        self.normalize = "l2"
        self.supports_dimension_override = False
        self.supports_batch = True
        self.max_batch_tokens = None

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_single(self, text: str) -> list[float]:
        ...

    def estimate_tokens(self, text: str) -> int:
        ...
```

3. Register it in `EmbeddingProviderFactory` by adding a branch for the new provider name.

4. The provider will be selectable via `embedding.provider = "my_provider"` in `.codegraph/config.toml`.

## Design Decisions

**LanceDB for storage.** A single embedded database handles symbols, edges, chunks, and vector search. No external database server required. Tradeoff: LanceDB's query capabilities are more limited than SQL, so filtering is done with simple WHERE clauses and in-memory post-processing.

**tree-sitter for parsing.** Concrete syntax trees give accurate position information and work across languages without requiring language-specific compilers. Tradeoff: tree-sitter grammars may lag behind language versions, and the `tree-sitter-languages` package bundles all grammars (large dependency).

**Protocol over ABC for ports.** Using `typing.Protocol` with `@runtime_checkable` means infrastructure classes don't need to explicitly inherit from port interfaces. This keeps infrastructure decoupled from domain at the import level. Tradeoff: no enforcement at class definition time — a missing method is only caught at runtime or by a type checker.

**Frozen dataclasses for Symbol and Edge.** Immutability makes these safe to use as dict keys and prevents accidental mutation during indexing. Generation stamping uses `dataclasses.replace()` to create new instances. Tradeoff: slightly more memory from creating copies during generation stamping.

**Mutable Chunk dataclass.** Unlike Symbol and Edge, Chunk is mutable because its `vector` and `has_vector` fields are populated in a second pass after embedding. This avoids creating a copy of every chunk just to attach a vector.

**Dual-key symbol identity.** `symbol_id` (position-based) is unique within a single index run but unstable across refactors. `symbol_key` (module-path-based) is stable across refactors within the same module. `symbol_key_exact` adds a signature hash to detect API changes. This three-tier scheme lets different operations choose the right stability/precision tradeoff.

**Edge identity excludes target.** `edge_id` is derived from source, location, and reference text — not the target. This is because target resolution is mutable (confidence improves over time), so the edge's identity should not change when its target is refined.

**Subprocess for git.** `SubprocessGitClient` shells out to `git` rather than using a Python git library. This avoids large dependencies (like `gitpython` or `pygit2`) and ensures compatibility with whatever git version is installed. Tradeoff: subprocess overhead per operation, but git operations are infrequent relative to parsing.

**Local ONNX as default embedding.** The local provider using ONNX Runtime with `nomic-embed-text-v1.5` works offline without API keys. API providers (OpenAI, Voyage) are available as opt-in alternatives. Tradeoff: local inference is slower and CPU-bound, but requires no external services.

**Polling-based file watcher.** `GitWatcher` polls `.git/HEAD` and `.git/index` mtimes rather than using inotify/FSEvents. This is simpler, works on all platforms, and avoids issues with git operations that create many rapid filesystem events. Tradeoff: detection latency bounded by poll interval.

**Single-flight reindex guard.** `ReindexGuard` ensures only one reindex runs at a time and coalesces pending requests. This prevents redundant work when multiple MCP tool calls detect staleness simultaneously.

**urllib over SDK packages.** API embedding providers use `urllib.request` directly instead of importing `openai` or `voyageai` packages. This keeps the dependency tree minimal — the only required packages are the ones in `pyproject.toml`. Tradeoff: manual retry logic and error handling instead of SDK conveniences.
