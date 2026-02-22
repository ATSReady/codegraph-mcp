"""Status, doctor, serve, and languages CLI commands."""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict

import click

from codegraph.application.index_progress_tracker import IndexProgressTracker
from codegraph.interface.cli.main import cli

_PROGRESS_TRACKER = IndexProgressTracker()


def get_progress_tracker() -> IndexProgressTracker:
    return _PROGRESS_TRACKER


def format_progress_snapshot(snapshot) -> dict:
    if snapshot is None:
        return {"active": False, "progress": None}
    return {"active": True, "progress": asdict(snapshot)}


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


    # Show last session token savings if available
    metrics_file = os.path.join(repo_root, ".codegraph", "metrics", "last-session.json")
    if os.path.exists(metrics_file):
        try:
            with open(metrics_file) as f:
                data = json.load(f)
            m = data["metrics"]
            click.echo(f"\nLast session: ~{m['total_saved']:,} tokens saved ({m['percent_saved']:.1f}%)")
        except Exception:
            pass

    if exit_stale and staleness.is_stale:
        sys.exit(3)


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--watch", is_flag=True, help="Watch progress until complete")
@click.option("--interval-ms", default=250, type=int, show_default=True, help="Watch interval in milliseconds")
@click.option("--repo-root", default=".", help="Repository root")
def progress(as_json, watch, interval_ms, repo_root):
    """Show active or most recent indexing progress."""
    _ = os.path.abspath(repo_root)
    tracker = get_progress_tracker()

    def _emit_once() -> dict:
        snapshot = tracker.get_active() or tracker.get_last()
        payload = format_progress_snapshot(snapshot)
        if as_json:
            click.echo(json.dumps(payload, indent=2))
        else:
            if not payload["active"]:
                click.echo("No progress data available.")
            else:
                p = payload["progress"]
                click.echo(
                    f"{p['mode']} {p['state']}: files {p['files_done']}/{p['files_total']} "
                    f"partitions {p['partitions_done']}/{p['partitions_total']}"
                )
        return payload

    if not watch:
        _emit_once()
        return

    while True:
        payload = _emit_once()
        p = payload["progress"]
        if (not payload["active"]) or p["state"] in {"completed", "failed", "cancelled"}:
            return
        time.sleep(max(interval_ms, 10) / 1000.0)


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
    """Start the MCP server via stdio transport."""
    import asyncio
    import logging

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    repo_root = os.path.abspath(repo_root)
    logger = logging.getLogger("codegraph")
    logger.info("Starting MCP server for %s", repo_root)

    from codegraph.infrastructure.storage.lancedb_store import LanceDBStore
    from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser
    from codegraph.infrastructure.parsers.chunker import CodeChunker
    from codegraph.infrastructure.git.client import SubprocessGitClient
    from codegraph.interface.mcp.server import CodegraphServer

    store_path = os.path.join(repo_root, ".codegraph", "index.lance")
    store = LanceDBStore(store_path) if os.path.exists(os.path.dirname(store_path)) else None
    parser = TreeSitterParser()
    chunker = CodeChunker()
    git_client = SubprocessGitClient(repo_root)

    embedding_provider = None
    try:
        from codegraph.infrastructure.embeddings.local_onnx import LocalOnnxProvider
        provider = LocalOnnxProvider()
        if provider._resolve_model_path():
            embedding_provider = provider
    except Exception:
        pass

    server = CodegraphServer(
        store=store,
        parser=parser,
        git_client=git_client,
        embedding_provider=embedding_provider,
        chunker=chunker,
        repo_root=repo_root,
    )

    asyncio.run(server.run())


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
