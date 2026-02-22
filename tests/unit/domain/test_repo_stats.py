"""Tests for RepoStats computation."""
import math
import pytest

from codegraph.domain.workspace import FileManifestEntry, ParseStatus, RepoStats


class TestRepoStatsFromManifest:
    def test_basic_computation(self):
        manifest = {
            "a.py": FileManifestEntry("a.py", "python", 0.0, 400, ParseStatus.OK),
            "b.py": FileManifestEntry("b.py", "python", 0.0, 1200, ParseStatus.OK),
            "c.py": FileManifestEntry("c.py", "python", 0.0, 800, ParseStatus.OK),
        }
        stats = RepoStats.from_manifest(manifest)

        assert stats.total_files == 3
        assert stats.total_bytes == 2400
        # tokens = ceil(bytes * 0.75)
        assert stats.total_tokens == math.ceil(2400 * 0.75)
        assert len(stats.per_file_tokens) == 3
        assert stats.per_file_tokens["a.py"] == math.ceil(400 * 0.75)
        assert stats.per_file_tokens["b.py"] == math.ceil(1200 * 0.75)

    def test_median_and_percentiles(self):
        manifest = {
            f"f{i}.py": FileManifestEntry(f"f{i}.py", "python", 0.0, size, ParseStatus.OK)
            for i, size in enumerate([100, 200, 300, 400, 500, 600, 700, 800, 900, 1000])
        }
        stats = RepoStats.from_manifest(manifest)
        assert stats.total_files == 10
        # Median of 10 items = avg of 5th and 6th = (500+600)/2 = 550 bytes
        assert stats.median_file_tokens == math.ceil(550 * 0.75)

    def test_empty_manifest(self):
        stats = RepoStats.from_manifest({})
        assert stats.total_files == 0
        assert stats.total_tokens == 0
        assert stats.per_file_tokens == {}
        assert stats.median_file_tokens == 0

    def test_single_file(self):
        manifest = {
            "only.py": FileManifestEntry("only.py", "python", 0.0, 600, ParseStatus.OK),
        }
        stats = RepoStats.from_manifest(manifest)
        assert stats.total_files == 1
        assert stats.median_file_tokens == math.ceil(600 * 0.75)
        assert stats.p75_file_tokens == math.ceil(600 * 0.75)
