"""Tests for CLI commands."""
import json
import os
import subprocess

import pytest
from click.testing import CliRunner

from codegraph.interface.cli.main import cli

# Import command modules so they register with the cli group
import codegraph.interface.cli.index_cmd  # noqa: F401
import codegraph.interface.cli.status_cmd  # noqa: F401


@pytest.fixture
def runner():
    return CliRunner()


class TestCliInit:
    def test_init_creates_config(self, runner, tmp_path):
        result = runner.invoke(cli, ["init", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".codegraph" / "config.toml").exists()

    def test_init_dry_run(self, runner, tmp_path):
        result = runner.invoke(cli, ["init", "--dry-run", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Would create" in result.output
        assert not (tmp_path / ".codegraph").exists()

    def test_init_already_exists(self, runner, tmp_path):
        (tmp_path / ".codegraph").mkdir()
        (tmp_path / ".codegraph" / "config.toml").write_text("# existing\n")
        result = runner.invoke(cli, ["init", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestCliStatus:
    def test_status_no_index(self, runner, tmp_path):
        (tmp_path / ".codegraph").mkdir()
        result = runner.invoke(cli, ["status", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0

    def test_status_json(self, runner, tmp_path):
        (tmp_path / ".codegraph").mkdir()
        result = runner.invoke(cli, ["status", "--json", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0

    def test_progress_command_exists(self, runner, tmp_path):
        (tmp_path / ".codegraph").mkdir()
        result = runner.invoke(cli, ["progress", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0



class TestStatusMetrics:
    def test_shows_last_session_metrics(self, tmp_path):
        """codegraph status shows last session's token savings."""
        metrics_dir = tmp_path / ".codegraph" / "metrics"
        metrics_dir.mkdir(parents=True)
        (metrics_dir / "last-session.json").write_text(json.dumps({
            "session_id": "test123",
            "metrics": {
                "total_saved": 42000,
                "percent_saved": 78.5,
                "tools": [],
                "total_naive": 53000,
                "total_actual": 11000,
            },
        }))
        from click.testing import CliRunner
        from codegraph.interface.cli.main import cli
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--repo-root", str(tmp_path)])
        assert "42,000" in result.output or "42000" in result.output


class TestCliDoctor:
    def test_doctor_no_config(self, runner, tmp_path):
        result = runner.invoke(cli, ["doctor", "--repo-root", str(tmp_path)])
        assert result.exit_code == 4  # Issues found

    def test_doctor_with_config(self, runner, tmp_path):
        (tmp_path / ".codegraph").mkdir()
        (tmp_path / ".codegraph" / "index.lance").mkdir()
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        result = runner.invoke(cli, ["doctor", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0


class TestCliLanguages:
    def test_languages_list(self, runner):
        result = runner.invoke(cli, ["languages"])
        assert result.exit_code == 0
        assert "python" in result.output

    def test_languages_json(self, runner):
        result = runner.invoke(cli, ["languages", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "languages" in data


class TestCliVersion:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCliIndexProgress:
    def test_index_progress_flag_prints_live_status(self, runner, tmp_path):
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "main.py").write_text("def hello():\n    return 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)
        (tmp_path / ".codegraph").mkdir(exist_ok=True)

        result = runner.invoke(cli, ["index", "--no-embed", "--progress", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0
        assert "progress" in result.output.lower()

    def test_second_index_run_reports_up_to_date(self, runner, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "main.py").write_text("def hello():\n    return 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)
        (tmp_path / ".codegraph").mkdir(exist_ok=True)

        first = runner.invoke(cli, ["index", "--no-embed", "--repo-root", str(tmp_path)])
        second = runner.invoke(cli, ["index", "--no-embed", "--repo-root", str(tmp_path)])
        assert first.exit_code == 0
        assert second.exit_code == 0
        assert "up to date" in second.output.lower()


class TestServeBootstrap:
    def test_bootstrap_repo_index_creates_config_and_index(self, tmp_path):
        from codegraph.interface.cli.status_cmd import bootstrap_repo_index

        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "main.py").write_text("def hello():\n    return 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)

        class _L:
            def info(self, *args, **kwargs):
                return None

        bootstrap_repo_index(str(tmp_path), _L())
        assert (tmp_path / ".codegraph" / "config.toml").exists()
        assert (tmp_path / ".codegraph" / "index.lance").exists()
