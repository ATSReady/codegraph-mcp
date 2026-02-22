"""Tests for metadata serialization round-trip."""
import pytest

from codegraph.domain.workspace import (
    FileManifestEntry,
    IndexMetadata,
    WorkspaceState,
    EmbeddingMetadata,
    ParseStatus,
)
from codegraph.infrastructure.storage.lancedb_store import (
    _serialize_metadata,
    _deserialize_metadata,
)


def _make_metadata(manifest: dict[str, FileManifestEntry] | None = None) -> IndexMetadata:
    return IndexMetadata(
        workspace_state=WorkspaceState(
            head_commit="abc123",
            index_base="abc123",
            worktree_dirty=False,
        ),
        embedding=EmbeddingMetadata(
            provider_id="none",
            model="none",
            model_revision=None,
            runtime="none",
            device="none",
            actual_dimension=0,
            requested_dimension=None,
            config_hash="",
            input_version=1,
            normalize="none",
        ),
        generation=1,
        file_manifest=manifest or {},
    )


class TestFileManifestSerialization:
    def test_round_trip_with_manifest(self):
        manifest = {
            "src/main.py": FileManifestEntry(
                file_path="src/main.py",
                language="python",
                mtime=1234567890.0,
                size=1500,
                parse_status=ParseStatus.OK,
            ),
            "src/utils.py": FileManifestEntry(
                file_path="src/utils.py",
                language="python",
                mtime=1234567891.0,
                size=800,
                parse_status=ParseStatus.WARN,
            ),
        }
        meta = _make_metadata(manifest)
        data = _serialize_metadata(meta)
        restored = _deserialize_metadata(data)

        assert len(restored.file_manifest) == 2
        assert restored.file_manifest["src/main.py"].size == 1500
        assert restored.file_manifest["src/utils.py"].size == 800
        assert restored.file_manifest["src/utils.py"].parse_status == ParseStatus.WARN

    def test_round_trip_empty_manifest(self):
        meta = _make_metadata({})
        data = _serialize_metadata(meta)
        restored = _deserialize_metadata(data)
        assert restored.file_manifest == {}

    def test_deserialize_missing_manifest_field(self):
        """Old serialized data without file_manifest should deserialize cleanly."""
        meta = _make_metadata()
        data = _serialize_metadata(meta)
        data.pop("file_manifest", None)
        restored = _deserialize_metadata(data)
        assert restored.file_manifest == {}
