"""CLI entry point for codegraph."""
from __future__ import annotations

import os
import sys

import click


@click.group()
@click.version_option(package_name="codegraph-mcp")
def cli():
    """codegraph - Code graph analysis and MCP server."""
    pass


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would be done without making changes")
@click.option("--repo-root", default=".", help="Repository root directory")
def init(dry_run, repo_root):
    """Initialize codegraph configuration for a repository."""
    repo_root = os.path.abspath(repo_root)
    config_dir = os.path.join(repo_root, ".codegraph")
    config_file = os.path.join(config_dir, "config.toml")

    if dry_run:
        click.echo(f"Would create: {config_dir}/")
        click.echo(f"Would create: {config_file}")
        return

    os.makedirs(config_dir, exist_ok=True)

    if not os.path.exists(config_file):
        default_config = (
            "# codegraph configuration\n"
            "[index]\n"
            'exclude = ["vendor/**", "generated/**", "**/*.min.js", "node_modules/**"]\n'
            "\n"
            "[server]\n"
            'auto_reindex = true\n'
            'log_level = "info"\n'
            "\n"
            "[embedding]\n"
            'provider = "local"\n'
        )
        with open(config_file, "w") as f:
            f.write(default_config)
        click.echo(f"Created {config_file}")
    else:
        click.echo(f"Config already exists: {config_file}")

    # Add .codegraph to .gitignore if not present
    gitignore = os.path.join(repo_root, ".gitignore")
    if os.path.exists(gitignore):
        content = open(gitignore).read()
        if ".codegraph/" not in content:
            with open(gitignore, "a") as f:
                f.write("\n# codegraph\n.codegraph/\n")
            click.echo("Added .codegraph/ to .gitignore")

    click.echo("Initialization complete. Run 'codegraph index' to build the index.")


def main():
    """Entry point for the CLI."""
    # Import command modules so their @cli.command() decorators register
    import codegraph.interface.cli.index_cmd  # noqa: F401
    import codegraph.interface.cli.status_cmd  # noqa: F401

    cli()
