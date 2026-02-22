"""Tests for naive token estimation in use cases."""
import os

import pytest

from codegraph.application.tools.get_snippet import GetSnippetUseCase
from codegraph.domain.metrics import estimate_tokens


class TestGetSnippetNaiveEstimation:
    def test_includes_naive_tokens(self, tmp_path):
        test_file = tmp_path / "big.py"
        content = "\n".join(f"line {i}: x = {i}" for i in range(100))
        test_file.write_text(content)

        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("big.py", start_line=10, end_line=15)

        assert "_naive_tokens" in result
        expected_naive = estimate_tokens(content)
        assert result["_naive_tokens"] == expected_naive
        assert estimate_tokens(result["content"]) < result["_naive_tokens"]

    def test_naive_tokens_for_full_file(self, tmp_path):
        test_file = tmp_path / "small.py"
        content = "x = 1\ny = 2\n"
        test_file.write_text(content)

        use_case = GetSnippetUseCase(str(tmp_path))
        result = use_case.execute("small.py")

        assert "_naive_tokens" in result
        # For small files, naive equals full file
        assert result["_naive_tokens"] == estimate_tokens(content)
