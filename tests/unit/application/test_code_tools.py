"""Tests for code access tool use cases."""

import os
import tempfile

import pytest
from unittest.mock import MagicMock

from codegraph.application.tools.get_snippet import GetSnippetUseCase
from codegraph.application.tools.get_diff import GetDiffUseCase
from codegraph.application.tools.get_changed_files import GetChangedFilesUseCase


class TestGetSnippetUseCase:
    def test_reads_full_file(self, tmp_path):
        f = tmp_path / "example.py"
        f.write_text("line1\nline2\nline3\n")
        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("example.py")
        assert result["total_lines"] == 3
        assert result["start_line"] == 1
        assert result["end_line"] == 3
        assert "line1" in result["content"]
        assert result["truncated"] is False

    def test_reads_line_range(self, tmp_path):
        lines = "\n".join(f"line{i}" for i in range(1, 11)) + "\n"
        f = tmp_path / "big.py"
        f.write_text(lines)
        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("big.py", start_line=3, end_line=5)
        assert result["start_line"] == 3
        assert result["end_line"] == 5
        assert "line3" in result["content"]
        assert "line5" in result["content"]
        assert "line2" not in result["content"]

    def test_file_not_found(self, tmp_path):
        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("nonexistent.py")
        assert "error" in result

    def test_max_lines_limit(self, tmp_path):
        lines = "\n".join(f"line{i}" for i in range(1, 201)) + "\n"
        f = tmp_path / "huge.py"
        f.write_text(lines)
        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("huge.py", max_lines=10)
        assert result["end_line"] == 10
        assert result["truncated"] is True

    def test_end_line_clamped_to_max_lines(self, tmp_path):
        lines = "\n".join(f"line{i}" for i in range(1, 201)) + "\n"
        f = tmp_path / "huge.py"
        f.write_text(lines)
        use_case = GetSnippetUseCase(str(tmp_path))
        # Request end_line=100 but max_lines=5 should clamp
        result = use_case.execute("huge.py", start_line=1, end_line=100, max_lines=5)
        assert result["end_line"] == 5

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("empty.py")
        assert result["total_lines"] == 0
        assert result["content"] == ""


class TestGetDiffUseCase:
    def test_with_changes(self):
        git = MagicMock()
        git.get_diff_unified.return_value = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
        use_case = GetDiffUseCase(git)
        result = use_case.execute("file.py")
        assert result["has_changes"] is True
        assert result["diff"] is not None
        git.get_diff_unified.assert_called_once_with("file.py", None, None, 3)

    def test_no_changes(self):
        git = MagicMock()
        git.get_diff_unified.return_value = None
        use_case = GetDiffUseCase(git)
        result = use_case.execute("file.py")
        assert result["has_changes"] is False
        assert result["diff"] is None

    def test_with_refs(self):
        git = MagicMock()
        git.get_diff_unified.return_value = "some diff"
        use_case = GetDiffUseCase(git)
        result = use_case.execute("file.py", base_ref="main", head_ref="feature", context_lines=5)
        git.get_diff_unified.assert_called_once_with("file.py", "main", "feature", 5)
        assert result["has_changes"] is True


class TestGetChangedFilesUseCase:
    def test_with_base_ref(self):
        git = MagicMock()
        git.get_diff_name_status.return_value = [
            {"file_path": "a.py", "status": "M"},
            {"file_path": "b.py", "status": "A"},
        ]
        use_case = GetChangedFilesUseCase(git)
        result = use_case.execute(base_ref="main")
        assert result["count"] == 2
        git.get_diff_name_status.assert_called_once_with("main", "HEAD")

    def test_without_base_ref(self):
        git = MagicMock()
        git.get_changed_files_since.return_value = [
            {"file_path": "c.py", "status": "M"},
        ]
        use_case = GetChangedFilesUseCase(git)
        result = use_case.execute()
        assert result["count"] == 1
        git.get_changed_files_since.assert_called_once_with(
            "HEAD", include_worktree=True,
        )

    def test_empty_changes(self):
        git = MagicMock()
        git.get_changed_files_since.return_value = []
        use_case = GetChangedFilesUseCase(git)
        result = use_case.execute()
        assert result["count"] == 0
        assert result["changes"] == []

    def test_custom_head_ref(self):
        git = MagicMock()
        git.get_diff_name_status.return_value = []
        use_case = GetChangedFilesUseCase(git)
        use_case.execute(base_ref="v1.0", head_ref="v2.0")
        git.get_diff_name_status.assert_called_once_with("v1.0", "v2.0")
