"""Get unified diff for a file."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.ports import GitClient


class GetDiffUseCase:
    """Retrieve a unified diff for a given file path."""

    def __init__(self, git_client: GitClient) -> None:
        self._git = git_client

    def execute(
        self,
        file_path: str,
        base_ref: Optional[str] = None,
        head_ref: Optional[str] = None,
        context_lines: int = 3,
    ) -> dict:
        diff = self._git.get_diff_unified(
            file_path, base_ref, head_ref, context_lines,
        )
        if diff is None:
            return {"file_path": file_path, "diff": None, "has_changes": False}
        return {
            "file_path": file_path,
            "diff": diff,
            "has_changes": True,
        }
