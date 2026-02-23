"""CLI integration tests for exit codes and CI behavior.

Tests that the CLI commands return the correct exit codes for CI pipelines:
- ``codegraph index --no-prompt`` exits 0 on success
- ``codegraph status --exit-stale`` exits 3 when the index is stale
- ``codegraph doctor`` exits 4 when issues are found
- ``codegraph index --break-stale-lock`` breaks dead locks
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from codegraph.interface.cli.main import cli

# Register command modules with the cli group
import codegraph.interface.cli.index_cmd  # noqa: F401
import codegraph.interface.cli.status_cmd  # noqa: F401


# ---------------------------------------------------------------------------
# Sample source content
# ---------------------------------------------------------------------------

SAMPLE_PYTHON = """\
class Greeter:
    def greet(self, name: str) -> str:
        return f"Hello, {name}"

def main():
    g = Greeter()
    print(g.greet("world"))
"""

SAMPLE_PYTHON_V2 = """\
class Greeter:
    def greet(self, name: str) -> str:
        return f"Hi, {name}"

    def farewell(self, name: str) -> str:
        return f"Bye, {name}"

def main():
    g = Greeter()
    print(g.greet("world"))
    print(g.farewell("world"))
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=path, capture_output=True, check=True,
    )


def _git_add_commit(path: Path, message: str = "commit") -> None:
    """Stage all files and commit."""
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=path, capture_output=True, check=True,
    )


def _write_sample_file(repo: Path, filename: str = "main.py", content: str = SAMPLE_PYTHON) -> None:
    """Write a sample Python file into the repo."""
    (repo / filename).write_text(content)


def _setup_repo_with_file(tmp_path: Path) -> Path:
    """Create a git repo with a committed Python file. Returns repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    _write_sample_file(repo)
    _git_add_commit(repo, "initial")
    # Create .codegraph dir so the index command can write its lock file
    (repo / ".codegraph").mkdir(exist_ok=True)
    return repo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def git_repo(tmp_path):
    """A git repository with a committed Python file."""
    return _setup_repo_with_file(tmp_path)


# ---------------------------------------------------------------------------
# Tests: codegraph index
# ---------------------------------------------------------------------------


class TestIndexCommand:
    """Test ``codegraph index`` exit codes."""

    def test_index_no_prompt_exits_0_on_success(self, runner, git_repo):
        """``codegraph index --no-prompt`` should exit 0 when indexing succeeds."""
        result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 0, f"stdout: {result.output}\nException: {result.exception}"
        assert "Indexed" in result.output

    def test_index_exits_2_when_locked(self, runner, git_repo):
        """``codegraph index`` should exit 2 when the index is locked."""
        # Create .codegraph dir and a lock file
        codegraph_dir = git_repo / ".codegraph"
        codegraph_dir.mkdir(exist_ok=True)
        lock_file = codegraph_dir / "index.lock"
        lock_info = {
            "pid": 999999,
            "hostname": "other-host",
            "user": "someone",
            "acquired_at": "2099-01-01T00:00:00+00:00",
            "command": "codegraph index",
        }
        lock_file.write_text(json.dumps(lock_info))

        result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 2

    def test_index_auto_breaks_stale_lock(self, runner, git_repo):
        """``codegraph index`` should auto-break stale locks even without the flag."""
        import socket

        codegraph_dir = git_repo / ".codegraph"
        codegraph_dir.mkdir(exist_ok=True)
        lock_file = codegraph_dir / "index.lock"
        lock_info = {
            "pid": 2147483647,  # dead PID on this host
            "hostname": socket.gethostname(),
            "user": "someone",
            "acquired_at": "2024-01-01T00:00:00+00:00",
            "command": "codegraph index",
        }
        lock_file.write_text(json.dumps(lock_info))

        result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 0, f"stdout: {result.output}\nException: {result.exception}"
        assert "Broke stale lock." in result.output

    def test_index_force_reindex(self, runner, git_repo):
        """``codegraph index --force`` should rebuild even if index exists."""
        # First index
        result1 = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--repo-root", str(git_repo),
        ])
        assert result1.exit_code == 0

        # Force reindex
        result2 = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--force", "--repo-root", str(git_repo),
        ])
        assert result2.exit_code == 0
        assert "Indexed" in result2.output


# ---------------------------------------------------------------------------
# Tests: codegraph index --break-stale-lock
# ---------------------------------------------------------------------------


class TestBreakStaleLock:
    """Test ``codegraph index --break-stale-lock`` behavior."""

    def test_break_stale_lock_dead_pid(self, runner, git_repo):
        """Should break a lock held by a dead process on the same host."""
        import socket

        codegraph_dir = git_repo / ".codegraph"
        codegraph_dir.mkdir(exist_ok=True)
        lock_file = codegraph_dir / "index.lock"

        # Use a PID that doesn't exist (very high number)
        lock_info = {
            "pid": 2147483647,
            "hostname": socket.gethostname(),
            "user": "test",
            "acquired_at": "2024-01-01T00:00:00+00:00",
            "command": "codegraph index",
        }
        lock_file.write_text(json.dumps(lock_info))

        result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed",
            "--break-stale-lock", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 0, f"stdout: {result.output}\nException: {result.exception}"
        assert "Broke stale lock" in result.output

    def test_break_stale_lock_old_timestamp(self, runner, git_repo):
        """Should break a lock with an old timestamp from a remote host."""
        codegraph_dir = git_repo / ".codegraph"
        codegraph_dir.mkdir(exist_ok=True)
        lock_file = codegraph_dir / "index.lock"

        # Lock from a different host, but very old
        lock_info = {
            "pid": 1234,
            "hostname": "some-other-host-that-does-not-exist",
            "user": "test",
            "acquired_at": "2020-01-01T00:00:00+00:00",
            "command": "codegraph index",
        }
        lock_file.write_text(json.dumps(lock_info))

        result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed",
            "--break-stale-lock", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 0, f"stdout: {result.output}\nException: {result.exception}"
        assert "Broke stale lock" in result.output

    def test_break_stale_lock_active_process(self, runner, git_repo):
        """Should refuse to break a lock held by an active process."""
        import socket

        codegraph_dir = git_repo / ".codegraph"
        codegraph_dir.mkdir(exist_ok=True)
        lock_file = codegraph_dir / "index.lock"

        # Use our own PID (definitely alive) with a recent timestamp
        lock_info = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "user": "test",
            "acquired_at": "2099-01-01T00:00:00+00:00",
            "command": "codegraph index",
        }
        lock_file.write_text(json.dumps(lock_info))

        result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed",
            "--break-stale-lock", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 2
        assert "active" in result.output.lower() or "cannot break" in result.output.lower()


# ---------------------------------------------------------------------------
# Tests: codegraph status --exit-stale
# ---------------------------------------------------------------------------


class TestStatusExitStale:
    """Test ``codegraph status --exit-stale`` exit code behavior."""

    def test_status_exit_stale_when_no_index(self, runner, git_repo):
        """Should exit 3 when there is no index at all (stale = no_index)."""
        # Ensure .codegraph directory exists for the store to open
        (git_repo / ".codegraph").mkdir(exist_ok=True)

        result = runner.invoke(cli, [
            "status", "--exit-stale", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 3, f"stdout: {result.output}\nException: {result.exception}"

    def test_status_exit_stale_after_new_commit(self, runner, git_repo):
        """Should exit 3 when index is behind HEAD (head_changed)."""
        # Build the index
        idx_result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--repo-root", str(git_repo),
        ])
        assert idx_result.exit_code == 0, f"Index failed: {idx_result.output}"

        # Make a new commit so HEAD changes
        _write_sample_file(git_repo, "main.py", SAMPLE_PYTHON_V2)
        _git_add_commit(git_repo, "update main.py")

        result = runner.invoke(cli, [
            "status", "--exit-stale", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 3
        assert "stale" in result.output.lower() or "yes" in result.output.lower()

    def test_status_exit_0_when_fresh(self, runner, git_repo):
        """Should exit 0 when index is up to date."""
        # Add .codegraph to .gitignore so the index files don't make
        # the worktree appear dirty after indexing.
        (git_repo / ".gitignore").write_text(".codegraph/\n")
        _git_add_commit(git_repo, "add gitignore")

        # Build the index at current HEAD
        idx_result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--repo-root", str(git_repo),
        ])
        assert idx_result.exit_code == 0

        result = runner.invoke(cli, [
            "status", "--exit-stale", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 0, f"stdout: {result.output}\nException: {result.exception}"

    def test_status_without_exit_stale_always_exits_0(self, runner, git_repo):
        """Without --exit-stale, status should always exit 0 even if stale."""
        (git_repo / ".codegraph").mkdir(exist_ok=True)

        result = runner.invoke(cli, [
            "status", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 0

    def test_status_json_output(self, runner, git_repo):
        """JSON output should include stale field."""
        (git_repo / ".codegraph").mkdir(exist_ok=True)

        result = runner.invoke(cli, [
            "status", "--json", "--repo-root", str(git_repo),
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "stale" in data


class TestProgressCommand:
    def test_progress_json_after_index(self, runner, git_repo):
        idx_result = runner.invoke(cli, [
            "index", "--no-prompt", "--no-embed", "--progress", "--repo-root", str(git_repo),
        ])
        assert idx_result.exit_code == 0

        progress_result = runner.invoke(cli, [
            "progress", "--json", "--repo-root", str(git_repo),
        ])
        assert progress_result.exit_code == 0
        payload = json.loads(progress_result.output)
        assert "active" in payload
        assert "progress" in payload


# ---------------------------------------------------------------------------
# Tests: codegraph doctor
# ---------------------------------------------------------------------------


class TestDoctorExitCodes:
    """Test ``codegraph doctor`` exit codes."""

    def test_doctor_exits_4_no_codegraph_dir(self, runner, tmp_path):
        """Should exit 4 when .codegraph directory is missing."""
        _init_git_repo(tmp_path)
        result = runner.invoke(cli, ["doctor", "--repo-root", str(tmp_path)])
        assert result.exit_code == 4
        assert "No .codegraph directory" in result.output

    def test_doctor_exits_4_no_index(self, runner, git_repo):
        """Should exit 4 when index directory is missing."""
        (git_repo / ".codegraph").mkdir(exist_ok=True)
        result = runner.invoke(cli, ["doctor", "--repo-root", str(git_repo)])
        assert result.exit_code == 4
        assert "No index directory" in result.output

    def test_doctor_exits_4_not_git_repo(self, runner, tmp_path):
        """Should exit 4 when not a git repo."""
        codegraph_dir = tmp_path / ".codegraph"
        codegraph_dir.mkdir()
        (codegraph_dir / "index.lance").mkdir()
        result = runner.invoke(cli, ["doctor", "--repo-root", str(tmp_path)])
        assert result.exit_code == 4
        assert "Not a git repository" in result.output

    def test_doctor_exits_4_with_lock(self, runner, git_repo):
        """Should exit 4 when a lock file exists."""
        codegraph_dir = git_repo / ".codegraph"
        codegraph_dir.mkdir(exist_ok=True)
        (codegraph_dir / "index.lance").mkdir()
        lock_info = {
            "pid": 12345,
            "hostname": "test-host",
            "user": "test",
            "acquired_at": "2024-01-01T00:00:00+00:00",
            "command": "codegraph index",
        }
        (codegraph_dir / "index.lock").write_text(json.dumps(lock_info))

        result = runner.invoke(cli, ["doctor", "--repo-root", str(git_repo)])
        assert result.exit_code == 4
        assert "Lock" in result.output or "PID" in result.output

    def test_doctor_exits_0_all_healthy(self, runner, git_repo):
        """Should exit 0 when everything is in order."""
        codegraph_dir = git_repo / ".codegraph"
        codegraph_dir.mkdir(exist_ok=True)
        (codegraph_dir / "index.lance").mkdir()

        result = runner.invoke(cli, ["doctor", "--repo-root", str(git_repo)])
        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_doctor_multiple_issues(self, runner, tmp_path):
        """Should report multiple issues at once."""
        # No .codegraph dir AND not a git repo
        result = runner.invoke(cli, ["doctor", "--repo-root", str(tmp_path)])
        assert result.exit_code == 4
        assert "Issues found" in result.output
