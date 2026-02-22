"""Get a code snippet from a file."""

from __future__ import annotations

import os


class GetSnippetUseCase:
    """Read a range of lines from a source file."""

    def __init__(self, repo_root: str) -> None:
        self._root = repo_root

    def execute(
        self,
        file_path: str,
        start_line: int = 1,
        end_line: int = 0,
        max_lines: int = 120,
    ) -> dict:
        full_path = os.path.join(self._root, file_path)
        if not os.path.exists(full_path):
            return {"error": f"File not found: {file_path}"}

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        total = len(all_lines)
        if end_line <= 0:
            end_line = min(start_line + max_lines - 1, total)
        end_line = min(end_line, start_line + max_lines - 1, total)

        snippet_lines = all_lines[start_line - 1 : end_line]
        return {
            "file_path": file_path,
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total,
            "content": "".join(snippet_lines),
            "truncated": end_line < total,
        }
