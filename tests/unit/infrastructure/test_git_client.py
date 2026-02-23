import os
import subprocess
import tempfile
import pytest
from unittest.mock import MagicMock
from codegraph.infrastructure.git.client import SubprocessGitClient


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    (repo / "file.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)
    return repo


class TestSubprocessGitClient:
    def test_is_git_repo(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        assert client.is_git_repo()

    def test_is_not_git_repo(self, tmp_path):
        client = SubprocessGitClient(str(tmp_path))
        assert not client.is_git_repo()

    def test_get_head_commit(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        head = client.get_head_commit()
        assert head is not None
        assert len(head) == 40

    def test_get_changed_files_since(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        (git_repo / "file.py").write_text("print('changed')\n")
        head = client.get_head_commit()
        changed = client.get_changed_files_since(head, include_worktree=True)
        assert any(f["file_path"] == "file.py" for f in changed)

    def test_get_changed_files_since_no_worktree(self, git_repo):
        """With include_worktree=False, only committed changes are returned."""
        client = SubprocessGitClient(str(git_repo))
        (git_repo / "file.py").write_text("print('changed')\n")
        head = client.get_head_commit()
        changed = client.get_changed_files_since(head, include_worktree=False)
        # No committed changes since head, only worktree dirty
        assert len(changed) == 0

    def test_get_untracked_files(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        (git_repo / "new.py").write_text("# new\n")
        untracked = client.get_untracked_files()
        assert "new.py" in untracked

    def test_is_dirty(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        assert not client.is_dirty()
        (git_repo / "file.py").write_text("changed\n")
        assert client.is_dirty()

    def test_get_git_head_mtime(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        mtime = client.get_git_head_mtime()
        assert mtime is not None
        assert mtime > 0

    def test_get_diff_name_status_with_renames(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        head1 = client.get_head_commit()
        subprocess.run(["git", "mv", "file.py", "renamed.py"], cwd=git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "rename"], cwd=git_repo, capture_output=True)
        changes = client.get_diff_name_status(head1)
        renamed = [c for c in changes if c["status"] == "renamed"]
        assert len(renamed) == 1
        assert renamed[0]["old_path"] == "file.py"
        assert renamed[0]["new_path"] == "renamed.py"

    def test_list_submodule_paths(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        client._run = MagicMock(return_value=MagicMock(returncode=0, stdout=" 123abc libs/a (heads/main)\n+456def deps/b (heads/dev)\n"))
        assert client.list_submodule_paths() == ["deps/b", "libs/a"]

    def test_filter_gitignored_files(self, git_repo):
        client = SubprocessGitClient(str(git_repo))
        (git_repo / ".gitignore").write_text("ignored.py\n")
        subprocess.run(["git", "add", ".gitignore"], cwd=git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "ignore"], cwd=git_repo, capture_output=True)
        filtered = client.filter_gitignored_files(["file.py", "ignored.py"])
        assert "file.py" in filtered
        assert "ignored.py" not in filtered
