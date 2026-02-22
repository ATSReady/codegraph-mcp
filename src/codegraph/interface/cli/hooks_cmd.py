"""Claude Code hook commands for displaying codegraph token savings."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import click

from codegraph.interface.cli.main import cli


def _get_branch() -> str:
    """Get current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _find_metrics_file() -> str | None:
    """Find the last-session.json metrics file relative to cwd."""
    path = os.path.join(os.getcwd(), ".codegraph", "metrics", "last-session.json")
    if os.path.exists(path):
        return path
    return None


def _load_metrics(path: str) -> dict | None:
    """Load and return metrics data from JSON file."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _format_tokens(n: int) -> str:
    """Format token count as human-readable string (e.g. ~5.2k, ~1.3M)."""
    if n >= 1_000_000:
        return f"~{n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"~{n / 1_000:.1f}k"
    else:
        return f"~{n}"


# ANSI codes
CYAN_BOLD = "\033[1;36m"
GREEN = "\033[32m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


@cli.command("on-stop")
def on_stop():
    """Hook: show compact token savings one-liner (for Claude Code Stop hook)."""
    metrics_path = _find_metrics_file()
    if not metrics_path:
        return

    data = _load_metrics(metrics_path)
    if not data or "metrics" not in data:
        return

    m = data["metrics"]
    total_saved = m.get("total_saved", 0)
    if total_saved == 0:
        return

    # Delta tracking: only show new savings since last report
    reported_path = os.path.join(
        os.path.dirname(metrics_path), "last-reported.json"
    )
    last_reported = 0
    try:
        if os.path.exists(reported_path):
            with open(reported_path) as f:
                last_reported = json.load(f).get("total_saved", 0)
    except Exception:
        pass

    delta = total_saved - last_reported
    if delta <= 0:
        return

    # Count total calls
    total_calls = sum(t.get("calls", 0) for t in m.get("tools", []))
    delta_calls = total_calls  # approximate — we track total, not delta calls

    branch = _get_branch()
    branch_part = f" · {branch}" if branch else ""

    line = (
        f" {CYAN_BOLD}codegraph{RESET}"
        f"  {GREEN}{_format_tokens(delta)} tokens saved{RESET}"
        f" · {delta_calls} calls"
        f"{DIM}{branch_part}{RESET}"
    )
    print(line, file=sys.stderr)

    # Persist current totals for next delta
    try:
        with open(reported_path, "w") as f:
            json.dump({"total_saved": total_saved, "total_calls": total_calls}, f)
    except Exception:
        pass

    # Exit non-zero so Claude Code displays the hook output
    os._exit(1)


@cli.command("on-session-end")
def on_session_end():
    """Hook: show full token savings table (for Claude Code SessionEnd hook)."""
    metrics_path = _find_metrics_file()
    if not metrics_path:
        return

    data = _load_metrics(metrics_path)
    if not data or "metrics" not in data:
        return

    m = data["metrics"]
    total_saved = m.get("total_saved", 0)
    if total_saved == 0:
        return

    tools = m.get("tools", [])
    branch = _get_branch()
    branch_part = f"  ·  {branch}" if branch else ""
    percent = m.get("percent_saved", 0.0)

    sep = f"{DIM}{'─' * 50}{RESET}"

    lines = [
        "",
        sep,
        f" {CYAN_BOLD}codegraph{RESET}  ·  session complete{DIM}{branch_part}{RESET}",
        sep,
    ]

    # Sort tools by tokens saved descending
    sorted_tools = sorted(tools, key=lambda t: t.get("tokens_saved", 0), reverse=True)
    for t in sorted_tools:
        saved = t.get("tokens_saved", 0)
        if saved == 0:
            continue
        name = t.get("tool", "unknown")
        calls = t.get("calls", 0)
        lines.append(
            f"  {name:<24} {calls}x  →  {GREEN}{_format_tokens(saved):>12} tokens saved{RESET}"
        )

    lines.append(sep)
    lines.append(
        f"  {BOLD}Total: {GREEN}{_format_tokens(total_saved)} tokens saved{RESET}"
        f"  {DIM}({percent:.1f}%){RESET}"
    )
    lines.append(sep)
    lines.append("")

    print("\n".join(lines), file=sys.stderr)

    # Clean up last-reported since session is ending
    reported_path = os.path.join(
        os.path.dirname(metrics_path), "last-reported.json"
    )
    try:
        if os.path.exists(reported_path):
            os.remove(reported_path)
    except Exception:
        pass

    # Exit non-zero so Claude Code displays the hook output
    os._exit(1)
