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
