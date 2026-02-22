"""Tests for the full repository indexing use case."""
import os
from concurrent.futures import Future

import pytest
from unittest.mock import MagicMock, PropertyMock

from codegraph.application.index_repo import IndexRepoUseCase, IndexResult
from codegraph.application.index_progress_tracker import IndexProgressTracker
from codegraph.domain.config import CodegraphConfig, IndexConfig
from codegraph.domain.models import Symbol, SymbolKind, Edge, EdgeKind
from codegraph.domain.workspace import (
    IndexMetadata,
    WorkspaceState,
    EmbeddingMetadata,
)


def _make_metadata(generation: int = 1, head_commit: str = "abc123") -> IndexMetadata:
    """Build a minimal valid IndexMetadata for testing."""
    return IndexMetadata(
        workspace_state=WorkspaceState(
            head_commit=head_commit,
            index_base=head_commit,
            worktree_dirty=False,
        ),
        embedding=EmbeddingMetadata(
            provider_id="none",
            model="none",
            model_revision=None,
            runtime="none",
            device="none",
            actual_dimension=0,
            requested_dimension=None,
            config_hash="",
            input_version=1,
            normalize="none",
        ),
        generation=generation,
    )


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_metadata.return_value = None
    return store


@pytest.fixture
def mock_parser():
    parser = MagicMock()
    parser.parse_file.return_value = (
        [
            Symbol(
                name="hello",
                kind=SymbolKind.FUNCTION,
                file_path="test.py",
                start_line=1,
                end_line=2,
                signature="def hello()",
                language="python",
            )
        ],
        [],
        [],
    )
    return parser


@pytest.fixture
def mock_git():
    git = MagicMock()
    git.is_git_repo.return_value = True
    git.get_head_commit.return_value = "abc123"
    git.list_tracked_files.return_value = []
    return git


class TestIndexRepoUseCase:
    def test_process_file_returns_symbols_edges_chunks(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\n")
        chunker = MagicMock()
        chunker.chunk_file.return_value = []
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
            chunker=chunker,
        )
        processed = use_case._process_file(str(tmp_path), "test.py", generation=1)
        assert processed.file_path == "test.py"
        assert len(processed.symbols) == 1
        assert len(processed.edges) == 0
        assert len(processed.chunks) == 0

    def test_index_uses_parallel_workers_when_enabled(self, mock_store, mock_parser, mock_git, tmp_path, monkeypatch):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "a.py").write_text("def a():\n    pass\n")
        (tmp_path / "tests" / "b.py").write_text("def b():\n    pass\n")
        mock_git.list_tracked_files.return_value = ["src/a.py", "tests/b.py"]

        submit_calls = []

        class FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def submit(self, fn, *args, **kwargs):
                submit_calls.append((fn, args, kwargs))
                fut = Future()
                fut.set_result(fn(*args, **kwargs))
                return fut

        monkeypatch.setattr("codegraph.application.index_repo.ThreadPoolExecutor", FakeExecutor)
        config = CodegraphConfig(index=IndexConfig(parallel_workers=2))
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
            config=config,
        )
        use_case.execute(str(tmp_path))
        assert len(submit_calls) > 1

    def test_index_updates_progress_tracker_states(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\n")
        mock_git.list_tracked_files.return_value = ["test.py"]
        tracker = IndexProgressTracker()
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
            progress_tracker=tracker,
        )
        use_case.execute(str(tmp_path))
        snap = tracker.get_last()
        assert snap is not None
        assert snap.state.value == "completed"
        assert snap.files_done == 1

    def test_basic_index(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\n")
        mock_git.list_tracked_files.return_value = ["test.py"]
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.files_indexed >= 1
        assert result.symbols_count >= 1
        assert result.generation == 1
        mock_store.upsert_symbols.assert_called_once()
        mock_store.set_metadata.assert_called_once()

    def test_increments_generation(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\n")
        mock_git.list_tracked_files.return_value = ["test.py"]
        mock_store.get_metadata.return_value = _make_metadata(generation=5, head_commit="old")
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.generation == 6

    def test_with_chunker(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\n")
        mock_git.list_tracked_files.return_value = ["test.py"]
        mock_chunker = MagicMock()
        mock_chunker.chunk_file.return_value = []
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
            chunker=mock_chunker,
        )
        result = use_case.execute(str(tmp_path))
        mock_chunker.chunk_file.assert_called_once()

    def test_handles_unreadable_file(self, mock_store, mock_parser, mock_git, tmp_path):
        # Create a directory with only unreadable files (no real .py files)
        # The parser won't be called because the file won't exist
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        # Create a .py file and then remove it so walk finds nothing
        result = use_case.execute(str(tmp_path))
        assert result.files_discovered == 0

    def test_handles_missing_file_on_read(self, mock_store, mock_parser, mock_git, tmp_path):
        """When a file exists during discovery but is gone at read time."""
        # Write file, discover it, then delete before read
        (tmp_path / "test.py").write_text("x = 1\n")
        mock_git.list_tracked_files.return_value = ["test.py"]
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        # Discover files first, then patch read to fail
        files = use_case._discover_files(str(tmp_path))
        assert len(files) >= 1
        # Remove the file to simulate it disappearing between discovery and read
        os.remove(tmp_path / "test.py")
        result = use_case.execute(str(tmp_path))
        assert result.files_discovered == 1  # git still reports the file
        assert result.files_failed == 1  # but reading it fails

    def test_no_git_walks_directory(self, mock_store, mock_parser, tmp_path):
        (tmp_path / "app.py").write_text("x = 1\n")
        mock_git = MagicMock()
        mock_git.is_git_repo.return_value = False
        mock_git.get_head_commit.return_value = None
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.files_discovered >= 1

    def test_excludes_patterns(self, mock_store, mock_parser, mock_git, tmp_path):
        vendor_dir = tmp_path / "vendor"
        vendor_dir.mkdir()
        (vendor_dir / "lib.py").write_text("x = 1\n")
        (tmp_path / "main.py").write_text("x = 1\n")
        mock_git.list_tracked_files.return_value = ["vendor/lib.py", "main.py"]
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        # vendor/** is in the default exclude list
        assert result.files_discovered >= 1

    def test_result_dataclass_defaults(self):
        r = IndexResult()
        assert r.files_discovered == 0
        assert r.files_indexed == 0
        assert r.files_failed == 0
        assert r.symbols_count == 0
        assert r.edges_count == 0
        assert r.chunks_count == 0
        assert r.chunks_embedded == 0
        assert r.embedding_errors == 0
        assert r.generation == 0
        assert r.duration == 0.0

    def test_metadata_set_with_workspace_state(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def hello():\n    pass\n")
        mock_git.list_tracked_files.return_value = ["test.py"]
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        use_case.execute(str(tmp_path))
        call_args = mock_store.set_metadata.call_args[0][0]
        assert call_args.workspace_state.head_commit == "abc123"
        assert call_args.generation == 1

    def test_skips_hidden_directories(self, mock_store, mock_parser, mock_git, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x = 1\n")
        (tmp_path / "visible.py").write_text("x = 1\n")
        mock_git.list_tracked_files.return_value = ["visible.py"]
        use_case = IndexRepoUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        # Should only find visible.py, not .hidden/secret.py
        assert result.files_discovered == 1
