"""Git client adapter using subprocess."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


class SubprocessGitClient:
    """Implements GitClient protocol via subprocess calls."""

    def __init__(self, repo_root: str) -> None:
        self._root = repo_root

    def _run(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + list(args),
            cwd=self._root,
            capture_output=True,
            text=True,
            check=check,
        )

    def is_git_repo(self) -> bool:
        result = self._run("rev-parse", "--is-inside-work-tree")
        return result.returncode == 0

    def get_head_commit(self) -> Optional[str]:
        result = self._run("rev-parse", "HEAD")
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def get_changed_files_since(self, base_ref: str, head_ref: str = "HEAD", include_worktree: bool = True) -> list[dict]:
        # Committed changes between base and head
        result = self._run("diff", "--name-only", f"{base_ref}..{head_ref}")
        committed = set(result.stdout.strip().splitlines()) if result.returncode == 0 else set()

        if include_worktree:
            # Unstaged changes in working tree
            result_wt = self._run("diff", "--name-only")
            unstaged = set(result_wt.stdout.strip().splitlines()) if result_wt.returncode == 0 else set()

            # Staged changes
            result_staged = self._run("diff", "--cached", "--name-only")
            staged = set(result_staged.stdout.strip().splitlines()) if result_staged.returncode == 0 else set()

            all_changed = committed | unstaged | staged
        else:
            all_changed = committed

        return [{"file_path": f, "status": "modified"} for f in sorted(all_changed) if f]

    def get_untracked_files(self) -> list[str]:
        result = self._run("ls-files", "--others", "--exclude-standard")
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f]

    def get_staged_files(self) -> list[str]:
        result = self._run("diff", "--cached", "--name-only")
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f]

    def get_status_porcelain(self) -> str:
        result = self._run("status", "--porcelain=v1", "-uno")
        return result.stdout if result.returncode == 0 else ""

    def get_diff_name_status(
        self, base_ref: str, head_ref: str = "HEAD", detect_renames: bool = True
    ) -> list[dict]:
        args = ["diff", "--name-status"]
        if detect_renames:
            args.append("-M")
        args.append(f"{base_ref}..{head_ref}")
        result = self._run(*args)
        if result.returncode != 0:
            return []

        changes = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("\t")
            status_code = parts[0][0]
            if status_code == "R" and len(parts) >= 3:
                changes.append({
                    "status": "renamed",
                    "old_path": parts[1],
                    "new_path": parts[2],
                })
            elif status_code == "A":
                changes.append({"status": "added", "file_path": parts[1]})
            elif status_code == "D":
                changes.append({"status": "deleted", "file_path": parts[1]})
            elif status_code == "M":
                changes.append({"status": "modified", "file_path": parts[1]})
        return changes

    def get_git_head_mtime(self) -> Optional[float]:
        head_path = Path(self._root) / ".git" / "HEAD"
        if head_path.exists():
            return head_path.stat().st_mtime
        return None

    def get_git_index_mtime(self) -> Optional[float]:
        index_path = Path(self._root) / ".git" / "index"
        if index_path.exists():
            return index_path.stat().st_mtime
        return None

    def is_dirty(self) -> bool:
        result = self._run("status", "--porcelain=v1")
        return bool(result.stdout.strip()) if result.returncode == 0 else False

    def get_default_branch(self) -> Optional[str]:
        result = self._run("symbolic-ref", "refs/remotes/origin/HEAD")
        if result.returncode == 0:
            ref = result.stdout.strip()
            return ref.split("/")[-1] if "/" in ref else ref
        for branch in ["main", "master"]:
            result = self._run("rev-parse", "--verify", f"refs/heads/{branch}")
            if result.returncode == 0:
                return branch
        return None

    def get_diff_unified(
        self,
        file_path: str,
        base_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
        context_lines: int = 3,
    ) -> Optional[str]:
        args = ["diff", f"-U{context_lines}"]
        if base_ref and head_ref:
            args.append(f"{base_ref}..{head_ref}")
        elif base_ref:
            args.append(base_ref)
        args.extend(["--", file_path])
        result = self._run(*args)
        if result.returncode != 0:
            return None
        return result.stdout if result.stdout.strip() else None

    def list_tracked_files(self) -> list[str]:
        """List all tracked files plus untracked non-ignored files."""
        result = self._run("ls-files", "--recurse-submodules")
        tracked = [f for f in result.stdout.strip().splitlines() if f] if result.returncode == 0 else []
        untracked = self.get_untracked_files()
        return sorted(set(tracked + untracked))

    def list_submodule_paths(self) -> list[str]:
        """Return submodule paths declared in this repository."""
        result = self._run("submodule", "status", "--recursive")
        if result.returncode != 0:
            return []
        paths: list[str] = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                paths.append(parts[1])
        return sorted(set(paths))

    def filter_gitignored_files(self, paths: list[str]) -> list[str]:
        """Remove files ignored by git (.gitignore, excludes, core.excludesFile)."""
        if not paths:
            return []
        # check-ignore returns 0 when at least one path is ignored, 1 when none are ignored.
        payload = "\n".join(paths) + "\n"
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--stdin"],
            cwd=self._root,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode not in (0, 1):
            return paths
        ignored = {line.strip() for line in result.stdout.splitlines() if line.strip()}
        if not ignored:
            return paths
        return [p for p in paths if p not in ignored]
