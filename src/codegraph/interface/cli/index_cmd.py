"""Index CLI commands."""
from __future__ import annotations

import os
import sys
import threading
import time

import click

from codegraph.interface.cli.main import cli


def _render_progress_line(snapshot) -> str:
    def _bar(done: int, total: int, width: int = 20) -> str:
        total = max(total, 1)
        done = max(0, min(done, total))
        filled = int((done / total) * width)
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    partition = snapshot.current_partition
    if partition is None and snapshot.partition_files_total:
        # If nothing is currently active (e.g., at completion), show a stable partition bar.
        partition = sorted(snapshot.partition_files_total.keys())[0]
    if partition:
        part_total = snapshot.partition_files_total.get(partition, 0)
        part_done = snapshot.partition_files_done.get(partition, 0)
        part_label = f"{partition} {_bar(part_done, part_total)} {part_done}/{part_total}"
    else:
        part_label = "n/a"

    return (
        f"progress: {snapshot.mode} {snapshot.state.value} "
        f"partition {part_label} "
        f"overall {snapshot.files_done}/{snapshot.files_total} "
        f"failed {snapshot.files_failed}"
    )


def _stream_progress(tracker, stop_event: threading.Event, state: dict | None = None) -> None:
    use_tty_bars = sys.stderr.isatty()
    overall_bar = None
    partition_bars = {}
    partition_positions = {}
    try:
        if use_tty_bars:
            try:
                from tqdm import tqdm  # type: ignore

                overall_bar = tqdm(
                    total=1,
                    desc="overall",
                    unit="file",
                    dynamic_ncols=True,
                    leave=True,
                    position=0,
                )
            except Exception:
                use_tty_bars = False
    except Exception:
        use_tty_bars = False
    if state is not None:
        state["used_tqdm"] = bool(use_tty_bars and overall_bar is not None)

    last_line = None
    while not stop_event.is_set():
        snap = tracker.get_active() or tracker.get_last()
        if snap is not None:
            if use_tty_bars and overall_bar is not None:
                overall_total = max(1, snap.files_total)
                if overall_bar.total != overall_total:
                    overall_bar.total = overall_total
                overall_bar.n = min(snap.files_done + snap.files_failed, overall_total)
                overall_bar.set_postfix_str(
                    f"{snap.state.value} failed={snap.files_failed}"
                )
                overall_bar.refresh()

                # One tqdm bar per partition, each with its own total/done counts.
                for idx, partition in enumerate(sorted(snap.partition_files_total.keys()), start=1):
                    if partition not in partition_bars:
                        from tqdm import tqdm  # type: ignore

                        partition_positions[partition] = idx
                        partition_bars[partition] = tqdm(
                            total=max(1, snap.partition_files_total.get(partition, 1)),
                            desc=f"partition:{partition}",
                            unit="file",
                            dynamic_ncols=True,
                            leave=True,
                            position=idx,
                        )
                    bar = partition_bars[partition]
                    bar.total = max(1, snap.partition_files_total.get(partition, 1))
                    bar.n = min(
                        snap.partition_files_done.get(partition, 0),
                        bar.total,
                    )
                    bar.refresh()
            else:
                line = _render_progress_line(snap)
                if line != last_line:
                    click.echo(line)
                    last_line = line
        time.sleep(0.1)

    for partition in sorted(partition_bars.keys()):
        partition_bars[partition].close()
    if overall_bar is not None:
        overall_bar.close()


@cli.command()
@click.option("--force", is_flag=True, help="Force full reindex even if up to date")
@click.option("--no-embed", is_flag=True, help="Skip embedding generation")
@click.option("--no-prompt", is_flag=True, help="Non-interactive mode for CI")
@click.option("--provider", type=str, default=None, help="Override embedding provider")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--break-stale-lock", is_flag=True, help="Break stale index locks")
@click.option("--progress", "show_progress", is_flag=True, help="Show indexing progress updates")
@click.option("--repo-root", default=".", help="Repository root")
def index(force, no_embed, no_prompt, provider, verbose, break_stale_lock, show_progress, repo_root):
    """Build or refresh the code index (incremental by default)."""
    repo_root = os.path.abspath(repo_root)

    # Check/break lock
    from codegraph.infrastructure.storage.lock import IndexLock

    lock_path = os.path.join(repo_root, ".codegraph", "index.lock")
    lock = IndexLock(lock_path)

    if lock.is_locked():
        # Always try safe stale-lock cleanup first (dead PID / invalid lock / old lock).
        stale_broken = lock.break_if_stale()
        if stale_broken:
            click.echo("Broke stale lock.")
        elif break_stale_lock:
            click.echo("Lock is active, cannot break.", err=True)
            sys.exit(2)
        else:
            click.echo("Index is locked. Use --break-stale-lock to force.", err=True)
            sys.exit(2)

    try:
        with lock:
            # Setup store
            from codegraph.infrastructure.storage.lancedb_store import LanceDBStore

            index_dir = os.path.join(repo_root, ".codegraph", "index.lance")
            os.makedirs(os.path.dirname(index_dir), exist_ok=True)
            store = LanceDBStore(index_dir)

            # Setup parser
            from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser

            parser = TreeSitterParser()

            # Setup git client
            from codegraph.infrastructure.git.client import SubprocessGitClient

            git = SubprocessGitClient(repo_root)

            # Setup chunker
            from codegraph.infrastructure.parsers.chunker import CodeChunker

            chunker = CodeChunker()

            # Setup embedding provider
            embedding_provider = None
            if not no_embed:
                try:
                    from codegraph.infrastructure.embeddings.factory import ProviderFactory
                    from codegraph.domain.config import EmbeddingConfig

                    config = EmbeddingConfig(provider=provider or "local")
                    embedding_provider = ProviderFactory.create(config)
                except Exception as e:
                    if verbose:
                        click.echo(f"Warning: Could not load embedding provider: {e}", err=True)

            # Run index/reindex
            from codegraph.application.index_repo import IndexRepoUseCase
            from codegraph.application.reindex import IncrementalReindexUseCase
            from codegraph.interface.cli.status_cmd import get_progress_tracker
            from codegraph.infrastructure.config_loader import load_config

            tracker = get_progress_tracker(repo_root)
            config = load_config(repo_root)
            metadata = store.get_metadata()
            is_incremental = (not force) and (metadata is not None)
            if is_incremental:
                use_case = IncrementalReindexUseCase(
                    store=store,
                    parser=parser,
                    git_client=git,
                    embedding_provider=embedding_provider,
                    chunker=chunker,
                    progress_tracker=tracker,
                    config=config,
                )
            else:
                use_case = IndexRepoUseCase(
                    store=store,
                    parser=parser,
                    git_client=git,
                    embedding_provider=embedding_provider,
                    chunker=chunker,
                    progress_tracker=tracker,
                    config=config,
                )

            if verbose:
                click.echo(f"Indexing {repo_root}...")
            stop_event = threading.Event()
            progress_thread = None
            progress_state = {}
            if show_progress:
                progress_thread = threading.Thread(
                    target=_stream_progress, args=(tracker, stop_event, progress_state), daemon=True
                )
                progress_thread.start()
            try:
                if is_incremental:
                    result = use_case.execute(repo_root)
                else:
                    result = use_case.execute(repo_root, force=force)
            finally:
                if show_progress and progress_thread is not None:
                    stop_event.set()
                    progress_thread.join(timeout=1.0)

            if is_incremental:
                if result.needs_full_index:
                    # Metadata disappeared or was unavailable: fallback to full index immediately.
                    full = IndexRepoUseCase(
                        store=store,
                        parser=parser,
                        git_client=git,
                        embedding_provider=embedding_provider,
                        chunker=chunker,
                        progress_tracker=tracker,
                        config=config,
                    )
                    result = full.execute(repo_root, force=True)
                    is_incremental = False
                elif result.files_changed == 0:
                    click.echo(f"Index is up to date (gen {metadata.generation}).")
                    return

            if is_incremental:
                click.echo(
                    f"Indexed {result.files_reindexed} changed files: "
                    f"{result.symbols_count} symbols, {result.edges_count} edges "
                    f"(gen {result.generation})"
                )
            else:
                click.echo(
                    f"Indexed {result.files_indexed} files: "
                    f"{result.symbols_count} symbols, {result.edges_count} edges, "
                    f"{result.chunks_count} chunks (gen {result.generation})"
                )
            if show_progress:
                used_tqdm = bool(progress_state.get("used_tqdm"))
                snap = tracker.get(result.operation_id) if result.operation_id else tracker.get_last()
                if snap and not used_tqdm:
                    click.echo(_render_progress_line(snap))
            if result.files_failed > 0:
                click.echo(f"  {result.files_failed} files failed", err=True)
            if hasattr(result, "chunks_embedded") and result.chunks_embedded > 0:
                click.echo(f"  {result.chunks_embedded} chunks embedded")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
