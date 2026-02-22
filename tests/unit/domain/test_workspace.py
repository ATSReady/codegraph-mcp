from codegraph.domain.workspace import (
    WorkspaceState, FileManifestEntry, PackageRoot,
    EmbeddingMetadata, FileDiagnostic, ParseStatus,
)


class TestWorkspaceState:
    def test_is_stale_when_head_changed(self):
        state = WorkspaceState(
            head_commit="abc1234",
            index_base="abc1234",
            worktree_dirty=False,
        )
        assert not state.is_stale_for_commit("abc1234")
        assert state.is_stale_for_commit("def5678")

    def test_dirty_state(self):
        state = WorkspaceState(
            head_commit="abc1234",
            index_base="abc1234",
            worktree_dirty=True,
            worktree_fingerprint="aabbccdd",
        )
        assert state.worktree_dirty


class TestFileDiagnostic:
    def test_parse_status_values(self):
        d = FileDiagnostic(
            file_path="src/auth.py",
            parse_status=ParseStatus.WARN,
            error_count=3,
            error_spans=[{"start_line": 10, "end_line": 12, "message": "unexpected token"}],
        )
        assert d.parse_status == ParseStatus.WARN
        assert d.error_count == 3


class TestEmbeddingMetadata:
    def test_provider_fingerprint(self):
        meta = EmbeddingMetadata(
            provider_id="local-onnx",
            model="nomic-embed-text-v1.5",
            model_revision="b0753ae",
            runtime="onnxruntime==1.17.0",
            device="cpu",
            actual_dimension=768,
            requested_dimension=None,
            config_hash="f2a9c1d3",
            input_version=1,
            normalize="l2",
        )
        assert meta.provider_id == "local-onnx"
        assert meta.actual_dimension == 768
