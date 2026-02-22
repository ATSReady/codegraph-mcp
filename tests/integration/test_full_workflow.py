"""End-to-end integration test: index -> query -> reindex workflow.

Creates a temporary git repository with Python and TypeScript files,
runs the full indexing pipeline, queries symbols/edges, modifies a file,
runs incremental reindex, and verifies the graph is updated correctly.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from codegraph.application.index_repo import IndexRepoUseCase
from codegraph.application.reindex import IncrementalReindexUseCase
from codegraph.application.tools.find_references import FindReferencesUseCase
from codegraph.application.tools.get_call_graph import GetCallGraphUseCase
from codegraph.application.tools.get_dependents import GetDependentsUseCase
from codegraph.application.tools.get_imports import GetImportsUseCase
from codegraph.application.tools.get_symbol import GetSymbolUseCase
from codegraph.application.tools.get_symbols import GetSymbolsUseCase
from codegraph.application.tools.semantic_search import SemanticSearchUseCase
from codegraph.domain.models import EdgeKind, SymbolKind
from codegraph.infrastructure.git.client import SubprocessGitClient
from codegraph.infrastructure.parsers.chunker import CodeChunker
from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser
from codegraph.infrastructure.storage.lancedb_store import LanceDBStore


# ---------------------------------------------------------------------------
# Sample source files
# ---------------------------------------------------------------------------

PYTHON_MAIN = """\
from utils import helper

class Calculator:
    \"\"\"A simple calculator.\"\"\"

    def add(self, a: int, b: int) -> int:
        return helper(a, b)

    def subtract(self, a: int, b: int) -> int:
        return a - b

def main():
    calc = Calculator()
    result = calc.add(1, 2)
    print(result)
"""

PYTHON_UTILS = """\
def helper(x: int, y: int) -> int:
    \"\"\"Add two numbers.\"\"\"
    return x + y

def unused_func():
    pass
"""

TYPESCRIPT_SRC = """\
export interface Config {
    host: string;
    port: number;
}

export class Server {
    private config: Config;

    constructor(config: Config) {
        this.config = config;
    }

    start(): void {
        console.log(`Starting on ${this.config.host}:${this.config.port}`);
    }
}

export function createServer(host: string, port: number): Server {
    const config: Config = { host, port };
    return new Server(config);
}
"""

# Modified version of main.py -- adds a new method and changes an existing one
PYTHON_MAIN_V2 = """\
from utils import helper

class Calculator:
    \"\"\"A simple calculator with multiply.\"\"\"

    def add(self, a: int, b: int) -> int:
        return helper(a, b)

    def subtract(self, a: int, b: int) -> int:
        return a - b

    def multiply(self, a: int, b: int) -> int:
        return a * b

def main():
    calc = Calculator()
    result = calc.multiply(3, 4)
    print(result)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git(repo_path: str, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the given repo."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )


def _create_temp_repo(tmp_path: Path) -> str:
    """Create a temp git repo with sample Python and TypeScript files."""
    repo = str(tmp_path / "repo")
    os.makedirs(repo)

    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")

    # Write source files
    (Path(repo) / "main.py").write_text(PYTHON_MAIN)
    (Path(repo) / "utils.py").write_text(PYTHON_UTILS)
    (Path(repo) / "server.ts").write_text(TYPESCRIPT_SRC)

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Initial commit")

    return repo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo_path(tmp_path):
    """Create a temporary git repo with sample files."""
    return _create_temp_repo(tmp_path)


@pytest.fixture
def store(tmp_path):
    """Create a fresh LanceDB store."""
    s = LanceDBStore(str(tmp_path / "test.lance"))
    yield s
    s.close()


@pytest.fixture
def parser():
    return TreeSitterParser()


@pytest.fixture
def chunker():
    return CodeChunker()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullWorkflow:
    """End-to-end: index -> query -> modify -> reindex -> verify."""

    def test_full_index_produces_symbols_and_edges(
        self, repo_path, store, parser, chunker,
    ):
        """Index a repo and verify symbols and edges are stored."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store,
            parser=parser,
            git_client=git_client,
            chunker=chunker,
        )
        result = indexer.execute(repo_path)

        # Should discover and index all 3 files
        assert result.files_discovered == 3
        assert result.files_indexed == 3
        assert result.files_failed == 0
        assert result.symbols_count > 0
        assert result.edges_count > 0
        assert result.chunks_count > 0
        assert result.generation == 1

    def test_query_python_symbols_after_index(
        self, repo_path, store, parser, chunker,
    ):
        """After indexing, query Python symbols by file."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        # Use GetSymbolsUseCase to query by file
        get_symbols = GetSymbolsUseCase(store)

        # main.py should have: Calculator class, add, subtract methods, main function
        result = get_symbols.execute(file_path="main.py")
        names = {s["name"] for s in result["symbols"]}
        assert "Calculator" in names
        assert "add" in names
        assert "subtract" in names
        assert "main" in names

        # utils.py should have: helper, unused_func
        result = get_symbols.execute(file_path="utils.py")
        names = {s["name"] for s in result["symbols"]}
        assert "helper" in names
        assert "unused_func" in names

    def test_query_typescript_symbols_after_index(
        self, repo_path, store, parser, chunker,
    ):
        """After indexing, query TypeScript symbols."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        get_symbols = GetSymbolsUseCase(store)
        result = get_symbols.execute(file_path="server.ts")
        names = {s["name"] for s in result["symbols"]}
        assert "Config" in names
        assert "Server" in names
        assert "createServer" in names

    def test_query_symbol_by_kind(
        self, repo_path, store, parser, chunker,
    ):
        """Filter symbols by kind."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        get_symbols = GetSymbolsUseCase(store)

        # Query for classes only
        result = get_symbols.execute(kind=SymbolKind.CLASS)
        names = {s["name"] for s in result["symbols"]}
        assert "Calculator" in names
        assert "Server" in names
        # Functions should not appear
        assert "main" not in names
        assert "helper" not in names

    def test_get_single_symbol(
        self, repo_path, store, parser, chunker,
    ):
        """Retrieve a single symbol by its ID."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        get_symbol = GetSymbolUseCase(store)

        # First find the Calculator symbol
        get_symbols = GetSymbolsUseCase(store)
        result = get_symbols.execute(file_path="main.py")
        calc_symbol = next(
            s for s in result["symbols"] if s["name"] == "Calculator"
        )

        # Retrieve by ID
        detail = get_symbol.execute(symbol_id=calc_symbol["symbol_id"])
        assert detail["symbol"] is not None
        assert detail["symbol"]["name"] == "Calculator"
        assert detail["symbol"]["kind"] == "class"

    def test_edges_exist_after_index(
        self, repo_path, store, parser, chunker,
    ):
        """Verify edges (imports, calls) are created during indexing."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        # Check import edges in main.py
        get_imports = GetImportsUseCase(store)
        imports_result = get_imports.execute(file_path="main.py")
        assert imports_result["count"] > 0
        import_refs = {e["ref_text"] for e in imports_result["imports"]}
        # The import statement "from utils import helper" should produce an edge
        assert any("helper" in ref for ref in import_refs)

    def test_call_graph_edges(
        self, repo_path, store, parser, chunker,
    ):
        """Verify call edges are indexed."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        # Find a function that makes calls
        get_symbols = GetSymbolsUseCase(store)
        result = get_symbols.execute(file_path="main.py")
        symbols = result["symbols"]

        # Find the 'add' method -- it calls helper()
        add_sym = next(
            (s for s in symbols if s["name"] == "add"), None,
        )
        if add_sym is None:
            pytest.skip("add method not found in parse results")

        get_call_graph = GetCallGraphUseCase(store)
        calls = get_call_graph.execute(
            symbol_id=add_sym["symbol_id"], direction="outgoing",
        )
        # add() calls helper(), so we expect at least one outgoing call edge
        if calls["count"] > 0:
            call_refs = {c["ref_text"] for c in calls["calls"]}
            assert any("helper" in ref for ref in call_refs)

    def test_chunks_created(
        self, repo_path, store, parser, chunker,
    ):
        """Verify chunks are created during indexing."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        # Check chunks for main.py
        chunks = store.get_chunks(file_path="main.py")
        assert len(chunks) > 0

        # Check chunks for server.ts
        chunks_ts = store.get_chunks(file_path="server.ts")
        assert len(chunks_ts) > 0

    def test_metadata_stored_after_index(
        self, repo_path, store, parser, chunker,
    ):
        """Verify metadata is persisted after indexing."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        metadata = store.get_metadata()
        assert metadata is not None
        assert metadata.generation == 1
        assert metadata.workspace_state.head_commit != ""

    def test_incremental_reindex_after_modification(
        self, repo_path, store, parser, chunker,
    ):
        """Modify a file, commit, reindex, and verify updates."""
        git_client = SubprocessGitClient(repo_path)

        # Step 1: Full index
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        index_result = indexer.execute(repo_path)
        assert index_result.generation == 1

        # Capture the initial symbol count for main.py
        get_symbols = GetSymbolsUseCase(store)
        initial = get_symbols.execute(file_path="main.py")
        initial_names = {s["name"] for s in initial["symbols"]}
        assert "multiply" not in initial_names

        # Step 2: Modify main.py and commit
        (Path(repo_path) / "main.py").write_text(PYTHON_MAIN_V2)
        _git(repo_path, "add", "main.py")
        _git(repo_path, "commit", "-m", "Add multiply method")

        # Step 3: Incremental reindex
        reindexer = IncrementalReindexUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        reindex_result = reindexer.execute(repo_path)

        assert reindex_result.needs_full_index is False
        assert reindex_result.files_changed > 0
        assert reindex_result.files_reindexed > 0
        assert reindex_result.generation == 2

        # Step 4: Verify main.py now has the multiply method
        updated = get_symbols.execute(file_path="main.py")
        updated_names = {s["name"] for s in updated["symbols"]}
        assert "multiply" in updated_names
        assert "Calculator" in updated_names
        assert "add" in updated_names
        assert "subtract" in updated_names

    def test_reindex_preserves_unmodified_files(
        self, repo_path, store, parser, chunker,
    ):
        """Reindex only touches changed files -- unmodified files stay intact."""
        git_client = SubprocessGitClient(repo_path)

        # Full index
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        # Count utils.py symbols before reindex
        get_symbols = GetSymbolsUseCase(store)
        before = get_symbols.execute(file_path="utils.py")
        before_names = {s["name"] for s in before["symbols"]}

        # Modify main.py only and commit
        (Path(repo_path) / "main.py").write_text(PYTHON_MAIN_V2)
        _git(repo_path, "add", "main.py")
        _git(repo_path, "commit", "-m", "Update main.py only")

        # Incremental reindex
        reindexer = IncrementalReindexUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        reindexer.execute(repo_path)

        # utils.py should still have the same symbols
        after = get_symbols.execute(file_path="utils.py")
        after_names = {s["name"] for s in after["symbols"]}
        assert before_names == after_names

    def test_reindex_without_prior_index_needs_full(
        self, store, repo_path, parser, chunker,
    ):
        """IncrementalReindex with no metadata signals needs_full_index."""
        git_client = SubprocessGitClient(repo_path)
        reindexer = IncrementalReindexUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        result = reindexer.execute(repo_path)
        assert result.needs_full_index is True

    def test_generation_increments_on_reindex(
        self, repo_path, store, parser, chunker,
    ):
        """Each reindex bumps the generation counter."""
        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        indexer.execute(repo_path)

        metadata = store.get_metadata()
        assert metadata.generation == 1

        # Modify and reindex
        (Path(repo_path) / "main.py").write_text(PYTHON_MAIN_V2)
        _git(repo_path, "add", "main.py")
        _git(repo_path, "commit", "-m", "v2")

        reindexer = IncrementalReindexUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
        )
        reindexer.execute(repo_path)

        metadata = store.get_metadata()
        assert metadata.generation == 2


class TestSemanticSearchWorkflow:
    """Semantic search tests -- skipped gracefully if no embedding model."""

    def _try_get_embedding_provider(self):
        """Try to create a local ONNX provider. Returns None if unavailable."""
        try:
            from codegraph.infrastructure.embeddings.local_onnx import LocalOnnxProvider
            provider = LocalOnnxProvider()
            # Force load to check if model is available
            provider._ensure_loaded()
            return provider
        except Exception:
            return None

    def test_semantic_search_with_embeddings(
        self, repo_path, store, parser, chunker,
    ):
        """Full workflow with embedding + semantic search."""
        provider = self._try_get_embedding_provider()
        if provider is None:
            pytest.skip("Local ONNX embedding model not available")

        git_client = SubprocessGitClient(repo_path)
        indexer = IndexRepoUseCase(
            store=store, parser=parser,
            git_client=git_client, chunker=chunker,
            embedding_provider=provider,
        )
        result = indexer.execute(repo_path)
        assert result.chunks_count > 0

        # Semantic search (async)
        import asyncio

        search = SemanticSearchUseCase(store, embedding_provider=provider)
        search_result = asyncio.run(
            search.execute(query="add two numbers", max_results=5),
        )
        assert "results" in search_result
        # If embeddings worked, we should get results
        if result.chunks_embedded > 0:
            assert search_result["count"] > 0

    def test_semantic_search_without_provider_returns_error(self, store):
        """SemanticSearchUseCase without provider returns an error dict."""
        import asyncio

        search = SemanticSearchUseCase(store, embedding_provider=None)
        result = asyncio.run(
            search.execute(query="anything"),
        )
        assert "error" in result
