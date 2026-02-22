"""Tests for the incremental reindex use case."""
import pytest
from unittest.mock import MagicMock

from codegraph.application.reindex import IncrementalReindexUseCase, ReindexResult
from codegraph.domain.models import Symbol, SymbolKind
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
    store.get_metadata.return_value = _make_metadata(generation=1, head_commit="abc123")
    return store


@pytest.fixture
def mock_parser():
    parser = MagicMock()
    parser.parse_file.return_value = (
        [
            Symbol(
                name="updated",
                kind=SymbolKind.FUNCTION,
                file_path="test.py",
                start_line=1,
                end_line=2,
                signature="def updated()",
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
    git.get_head_commit.return_value = "def456"
    git.get_changed_files_since.return_value = [
        {"file_path": "test.py", "status": "modified"},
    ]
    return git


class TestIncrementalReindexUseCase:
    def test_basic_reindex(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def updated():\n    pass\n")
        use_case = IncrementalReindexUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.files_reindexed == 1
        assert result.symbols_count == 1
        assert result.generation == 2
        mock_store.delete_symbols_by_file.assert_called_with("test.py")

    def test_no_changes(self, mock_store, mock_parser, mock_git, tmp_path):
        mock_git.get_changed_files_since.return_value = []
        use_case = IncrementalReindexUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.files_changed == 0
        assert result.files_reindexed == 0

    def test_needs_full_index_when_no_metadata(self, mock_parser, mock_git, tmp_path):
        store = MagicMock()
        store.get_metadata.return_value = None
        use_case = IncrementalReindexUseCase(
            store=store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.needs_full_index is True

    def test_handles_deletions(self, mock_store, mock_parser, mock_git, tmp_path):
        mock_git.get_changed_files_since.return_value = [
            {"file_path": "deleted.py", "status": "deleted"},
        ]
        use_case = IncrementalReindexUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.files_deleted == 1
        mock_store.delete_symbols_by_file.assert_called_with("deleted.py")

    def test_handles_mixed_changes(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "modified.py").write_text("x = 1\n")
        mock_git.get_changed_files_since.return_value = [
            {"file_path": "modified.py", "status": "modified"},
            {"file_path": "removed.py", "status": "deleted"},
        ]
        use_case = IncrementalReindexUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        result = use_case.execute(str(tmp_path))
        assert result.files_reindexed == 1
        assert result.files_deleted == 1

    def test_updates_metadata_head_commit(self, mock_store, mock_parser, mock_git, tmp_path):
        (tmp_path / "test.py").write_text("def updated():\n    pass\n")
        use_case = IncrementalReindexUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=mock_git,
        )
        use_case.execute(str(tmp_path))
        # Verify set_metadata was called
        mock_store.set_metadata.assert_called_once()
        saved = mock_store.set_metadata.call_args[0][0]
        assert saved.workspace_state.head_commit == "def456"
        assert saved.generation == 2

    def test_result_dataclass_defaults(self):
        r = ReindexResult()
        assert r.files_changed == 0
        assert r.files_reindexed == 0
        assert r.files_deleted == 0
        assert r.files_failed == 0
        assert r.symbols_count == 0
        assert r.edges_count == 0
        assert r.generation == 0
        assert r.embedding_errors == 0
        assert r.needs_full_index is False
        assert r.duration == 0.0

    def test_no_git_client_returns_no_changes(self, mock_store, mock_parser, tmp_path):
        use_case = IncrementalReindexUseCase(
            store=mock_store,
            parser=mock_parser,
            git_client=None,
        )
        result = use_case.execute(str(tmp_path))
        assert result.files_changed == 0
