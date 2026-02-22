"""Get changed files from git."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.ports import GitClient


class GetChangedFilesUseCase:
    """List files changed between two git refs or in the working tree."""

    def __init__(self, git_client: GitClient) -> None:
        self._git = git_client

    def execute(
        self,
        base_ref: Optional[str] = None,
        head_ref: str = "HEAD",
        include_worktree: bool = True,
    ) -> dict:
        if base_ref:
            changes = self._git.get_diff_name_status(base_ref, head_ref)
        else:
            changes = self._git.get_changed_files_since(
                "HEAD", include_worktree=include_worktree,
            )
        return {
            "changes": changes,
            "count": len(changes),
            "_naive_tokens": 0,
        }
