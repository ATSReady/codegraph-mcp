"""Global install/configuration command for MCP clients."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import click

from codegraph.interface.cli.main import cli


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _upsert_codex_mcp(path: Path, codegraph_bin: str, timeout_sec: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = (
        "[mcp_servers.codegraph]\n"
        f'command = "{codegraph_bin}"\n'
        'args = ["serve"]\n'
        f"startup_timeout_sec = {timeout_sec}\n"
    )
    if not path.exists():
        path.write_text(block, encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8")
    pattern = r"(?ms)^\[mcp_servers\.codegraph\]\n(?:.*\n)*?(?=^\[|\Z)"
    if re.search(pattern, text):
        new_text = re.sub(pattern, block + "\n", text)
    else:
        sep = "" if text.endswith("\n") else "\n"
        new_text = text + sep + "\n" + block
    path.write_text(new_text, encoding="utf-8")


def _configure_claude(codegraph_bin: str, timeout_sec: int) -> None:
    settings_path = Path.home() / ".claude" / "settings.json"
    data = _read_json(settings_path)
    data.setdefault("env", {})
    data["env"]["MCP_TIMEOUT"] = str(timeout_sec * 1000)
    _write_json(settings_path, data)

    if shutil.which("claude"):
        payload = json.dumps(
            {
                "type": "stdio",
                "command": codegraph_bin,
                "args": ["serve"],
            }
        )
        try:
            subprocess.run(
                ["claude", "mcp", "add-json", "codegraph", payload, "--scope", "user"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def _configure_codex(codegraph_bin: str, timeout_sec: int) -> None:
    config_path = Path.home() / ".codex" / "config.toml"
    _upsert_codex_mcp(config_path, codegraph_bin, timeout_sec)


def _configure_gemini(codegraph_bin: str, timeout_sec: int) -> None:
    settings_path = Path.home() / ".gemini" / "settings.json"
    data = _read_json(settings_path)
    data.setdefault("mcpServers", {})
    data["mcpServers"]["codegraph"] = {
        "command": codegraph_bin,
        "args": ["serve"],
        "startup_timeout_sec": timeout_sec,
        "startupTimeoutSec": timeout_sec,
    }
    _write_json(settings_path, data)


def _configure_opencode(codegraph_bin: str, timeout_sec: int) -> None:
    config_path = Path.home() / ".config" / "opencode" / "opencode.json"
    data = _read_json(config_path)
    data.setdefault("mcp", {})
    data["mcp"]["codegraph"] = {
        "type": "local",
        "command": [codegraph_bin, "serve"],
        "startup_timeout_sec": timeout_sec,
        "startupTimeoutSec": timeout_sec,
    }
    _write_json(config_path, data)


@cli.command("install")
@click.option(
    "--timeout-sec",
    default=30,
    show_default=True,
    type=int,
    help="MCP startup timeout in seconds for configured clients.",
)
@click.option("--codegraph-bin", default=None, help="Override codegraph binary path.")
def install_cmd(timeout_sec: int, codegraph_bin: str | None) -> None:
    """Configure codegraph globally for supported AI clients."""
    if timeout_sec <= 0:
        raise click.ClickException("--timeout-sec must be > 0")

    resolved_bin = codegraph_bin or shutil.which("codegraph")
    if not resolved_bin:
        # Keep command useful even in dev/test environments.
        resolved_bin = os.path.abspath(sys.argv[0])

    _configure_claude(resolved_bin, timeout_sec)
    _configure_codex(resolved_bin, timeout_sec)
    _configure_gemini(resolved_bin, timeout_sec)
    _configure_opencode(resolved_bin, timeout_sec)

    click.echo("Configured codegraph MCP for Claude, Codex, Gemini, and OpenCode.")
    click.echo(f"Set startup timeout to {timeout_sec}s.")
    click.echo("")
    click.echo("If your coding agent reports MCP startup timeout for codegraph:")
    click.echo("1. Exit the coding session.")
    click.echo("2. Run this in your repo before starting a new session:")
    click.echo("   codegraph init && codegraph index --progress")
