"""Index and reindex CLI commands."""
from __future__ import annotations

import os
import sys

import click

from codegraph.interface.cli.main import cli


@cli.command()
@click.option("--force", is_flag=True, help="Force full reindex even if up to date")
@click.option("--no-embed", is_flag=True, help="Skip embedding generation")
@click.option("--no-prompt", is_flag=True, help="Non-interactive mode for CI")
@click.option("--provider", type=str, default=None, help="Override embedding provider")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--break-stale-lock", is_flag=True, help="Break stale index locks")
@click.option("--repo-root", default=".", help="Repository root")
def index(force, no_embed, no_prompt, provider, verbose, break_stale_lock, repo_root):
    """Build or rebuild the code index."""
    repo_root = os.path.abspath(repo_root)

    # Check/break lock
    from codegraph.infrastructure.storage.lock import IndexLock

    lock_path = os.path.join(repo_root, ".codegraph", "index.lock")
    lock = IndexLock(lock_path)

    if lock.is_locked():
        if break_stale_lock:
            if lock.break_if_stale():
                click.echo("Broke stale lock.")
            else:
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

            # Run index
            from codegraph.application.index_repo import IndexRepoUseCase

            use_case = IndexRepoUseCase(
                store=store,
                parser=parser,
                git_client=git,
                embedding_provider=embedding_provider,
                chunker=chunker,
            )

            if verbose:
                click.echo(f"Indexing {repo_root}...")

            result = use_case.execute(repo_root, force=force)

            click.echo(
                f"Indexed {result.files_indexed} files: "
                f"{result.symbols_count} symbols, {result.edges_count} edges, "
                f"{result.chunks_count} chunks (gen {result.generation})"
            )
            if result.files_failed > 0:
                click.echo(f"  {result.files_failed} files failed", err=True)
            if result.chunks_embedded > 0:
                click.echo(f"  {result.chunks_embedded} chunks embedded")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--repo-root", default=".", help="Repository root")
def reindex(verbose, repo_root):
    """Incrementally reindex changed files."""
    repo_root = os.path.abspath(repo_root)

    from codegraph.infrastructure.storage.lock import IndexLock

    lock_path = os.path.join(repo_root, ".codegraph", "index.lock")
    lock = IndexLock(lock_path)

    try:
        with lock:
            from codegraph.infrastructure.storage.lancedb_store import LanceDBStore
            from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser
            from codegraph.infrastructure.git.client import SubprocessGitClient
            from codegraph.infrastructure.parsers.chunker import CodeChunker
            from codegraph.application.reindex import IncrementalReindexUseCase

            index_dir = os.path.join(repo_root, ".codegraph", "index.lance")
            store = LanceDBStore(index_dir)
            parser = TreeSitterParser()
            git = SubprocessGitClient(repo_root)
            chunker = CodeChunker()

            use_case = IncrementalReindexUseCase(
                store=store,
                parser=parser,
                git_client=git,
                chunker=chunker,
            )
            result = use_case.execute(repo_root)

            if result.needs_full_index:
                click.echo("No existing index. Run 'codegraph index' first.")
                sys.exit(1)

            click.echo(
                f"Reindexed {result.files_reindexed} files: "
                f"{result.symbols_count} symbols, {result.edges_count} edges "
                f"(gen {result.generation})"
            )

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
