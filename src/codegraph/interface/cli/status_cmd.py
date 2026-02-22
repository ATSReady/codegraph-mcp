"""Status, doctor, serve, and languages CLI commands."""
from __future__ import annotations

import json
import os
import sys

import click

from codegraph.interface.cli.main import cli


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--exit-stale", is_flag=True, help="Exit code 3 if index is stale")
@click.option("--repo-root", default=".", help="Repository root")
def status(as_json, exit_stale, repo_root):
    """Show index status and health."""
    repo_root = os.path.abspath(repo_root)
    index_dir = os.path.join(repo_root, ".codegraph", "index.lance")

    from codegraph.infrastructure.storage.lancedb_store import LanceDBStore
    from codegraph.infrastructure.git.client import SubprocessGitClient
    from codegraph.application.tools.get_repo_overview import GetRepoOverviewUseCase
    from codegraph.application.staleness import StalenessChecker

    store = LanceDBStore(index_dir)
    git = SubprocessGitClient(repo_root)

    overview = GetRepoOverviewUseCase(store, git).execute()
    staleness = StalenessChecker(store, git).check()
    overview["stale"] = staleness.is_stale
    overview["stale_reason"] = staleness.reason

    if as_json:
        click.echo(json.dumps(overview, indent=2))
    else:
        if overview.get("indexed"):
            click.echo(f"Index: gen {overview.get('generation', '?')}")
            click.echo(f"Files: {overview.get('file_count', '?')}")
            click.echo(
                f"Stale: {'yes' if staleness.is_stale else 'no'}"
                + (f" ({staleness.reason})" if staleness.is_stale else "")
            )
        else:
            click.echo("No index found. Run 'codegraph index' to build one.")

    if exit_stale and staleness.is_stale:
        sys.exit(3)


@cli.command()
@click.option("--repo-root", default=".", help="Repository root")
def doctor(repo_root):
    """Run health checks on the index."""
    repo_root = os.path.abspath(repo_root)
    issues = []

    # Check config dir
    config_dir = os.path.join(repo_root, ".codegraph")
    if not os.path.isdir(config_dir):
        issues.append("No .codegraph directory. Run 'codegraph init'.")

    # Check index
    index_dir = os.path.join(repo_root, ".codegraph", "index.lance")
    if not os.path.isdir(index_dir):
        issues.append("No index directory. Run 'codegraph index'.")

    # Check lock
    lock_path = os.path.join(repo_root, ".codegraph", "index.lock")
    if os.path.exists(lock_path):
        from codegraph.infrastructure.storage.lock import IndexLock

        lock = IndexLock(lock_path)
        info = lock.read_lock_info()
        if info:
            issues.append(f"Lock held by PID {info.pid} on {info.hostname}")

    # Check git
    from codegraph.infrastructure.git.client import SubprocessGitClient

    git = SubprocessGitClient(repo_root)
    if not git.is_git_repo():
        issues.append("Not a git repository.")

    if issues:
        click.echo("Issues found:")
        for issue in issues:
            click.echo(f"  - {issue}")
        sys.exit(4)
    else:
        click.echo("All checks passed.")


@cli.command()
@click.option("--repo-root", default=".", help="Repository root")
@click.option("--log-level", default="info", help="Log level")
@click.option("--no-watch", is_flag=True, help="Disable file watchers")
def serve(repo_root, log_level, no_watch):
    """Start the MCP server."""
    import asyncio
    import logging

    logging.basicConfig(level=getattr(logging, log_level.upper(), logging.INFO))
    repo_root = os.path.abspath(repo_root)

    click.echo(f"Starting MCP server for {repo_root}...")
    click.echo("MCP server not yet implemented.", err=True)
    sys.exit(1)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def languages(as_json):
    """List supported programming languages."""
    from codegraph.infrastructure.parsers.languages import available_languages

    langs = available_languages()

    if as_json:
        click.echo(json.dumps({"languages": langs}, indent=2))
    else:
        for lang in langs:
            exts = ", ".join(lang["extensions"])
            click.echo(f"  {lang['name']}: {exts}")
