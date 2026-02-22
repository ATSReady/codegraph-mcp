"""Tests for LocalOnnxProvider."""
import pytest
from unittest.mock import MagicMock, patch
import numpy as np

from codegraph.infrastructure.embeddings.local_onnx import LocalOnnxProvider
from codegraph.infrastructure.embeddings.base import normalize_l2


class TestLocalOnnxProvider:
    """Tests for the local ONNX embedding provider."""

    def test_init_defaults(self):
        provider = LocalOnnxProvider()
        assert provider.model_name == "nomic-embed-text-v1.5"
        assert provider.dimension == 768
        assert provider.name == "local"
        assert provider.max_tokens == 8192
        assert provider.normalize == "l2"
        assert provider.supports_batch is True

    def test_init_custom_dimension(self):
        provider = LocalOnnxProvider(dimension=384)
        assert provider.dimension == 384

    def test_init_no_normalize(self):
        provider = LocalOnnxProvider(do_normalize=False)
        assert provider.normalize == "none"

    def test_embed_without_model_raises(self):
        provider = LocalOnnxProvider(model_path="/nonexistent/model.onnx")
        with pytest.raises(RuntimeError, match="not found"):
            provider._embed_sync(["test"])

    @pytest.mark.asyncio
    async def test_embed_batch_without_model_raises(self):
        provider = LocalOnnxProvider(model_path="/nonexistent/model.onnx")
        with pytest.raises(RuntimeError, match="not found"):
            await provider.embed_batch(["test"])

    def test_embed_empty_returns_empty(self):
        provider = LocalOnnxProvider()
        provider._session = MagicMock()  # Skip model loading
        result = provider._embed_sync([])
        assert result.vectors == []
        assert result.dimension == 768

    def test_embed_with_mocked_session(self):
        provider = LocalOnnxProvider(dimension=4, do_normalize=True)
        mock_session = MagicMock()
        # Return shape (batch, dim) embeddings
        mock_session.run.return_value = [np.array([[1.0, 2.0, 3.0, 4.0]])]
        provider._session = mock_session
        provider._tokenizer = None  # Use fallback tokenization

        result = provider._embed_sync(["hello world"])
        assert len(result.vectors) == 1
        assert len(result.vectors[0]) == 4
        # Should be L2 normalized
        norm = sum(x * x for x in result.vectors[0]) ** 0.5
        assert abs(norm - 1.0) < 1e-5

    def test_embed_multiple_with_mocked_session(self):
        provider = LocalOnnxProvider(dimension=4, do_normalize=False)
        mock_session = MagicMock()
        mock_session.run.return_value = [
            np.array([
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ])
        ]
        provider._session = mock_session
        provider._tokenizer = None

        result = provider._embed_sync(["hello", "world"])
        assert len(result.vectors) == 2
        assert result.vectors[0] == [1.0, 0.0, 0.0, 0.0]
        assert result.vectors[1] == [0.0, 1.0, 0.0, 0.0]

    @pytest.mark.asyncio
    async def test_embed_single_async(self):
        provider = LocalOnnxProvider(dimension=4, do_normalize=False)
        mock_session = MagicMock()
        mock_session.run.return_value = [np.array([[1.0, 2.0, 3.0, 4.0]])]
        provider._session = mock_session
        provider._tokenizer = None

        vec = await provider.embed_single("test")
        assert len(vec) == 4
        assert vec == [1.0, 2.0, 3.0, 4.0]

    @pytest.mark.asyncio
    async def test_embed_batch_async(self):
        provider = LocalOnnxProvider(dimension=4, do_normalize=False)
        mock_session = MagicMock()
        mock_session.run.return_value = [
            np.array([
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ])
        ]
        provider._session = mock_session
        provider._tokenizer = None

        vecs = await provider.embed_batch(["hello", "world"])
        assert len(vecs) == 2

    def test_dimension_truncation(self):
        provider = LocalOnnxProvider(dimension=2, do_normalize=False)
        mock_session = MagicMock()
        mock_session.run.return_value = [np.array([[1.0, 2.0, 3.0, 4.0]])]
        provider._session = mock_session
        provider._tokenizer = None

        result = provider._embed_sync(["test"])
        assert len(result.vectors[0]) == 2
        assert result.vectors[0] == [1.0, 2.0]

    def test_3d_output_mean_pooling(self):
        """Test that 3D model output (batch, seq, dim) is mean-pooled."""
        provider = LocalOnnxProvider(dimension=3, do_normalize=False)
        mock_session = MagicMock()
        # Shape (1, 2, 3) - batch=1, seq_len=2, dim=3
        mock_session.run.return_value = [
            np.array([[[2.0, 4.0, 6.0], [4.0, 8.0, 12.0]]])
        ]
        provider._session = mock_session
        provider._tokenizer = None

        # Mock _tokenize to return matching attention mask (seq_len=2)
        provider._tokenize = lambda texts: {
            "input_ids": np.zeros((len(texts), 2), dtype=np.int64),
            "attention_mask": np.ones((len(texts), 2), dtype=np.int64),
        }

        result = provider._embed_sync(["test"])
        assert len(result.vectors) == 1
        # Mean of [2,4,6] and [4,8,12] = [3,6,9]
        vec = result.vectors[0]
        assert abs(vec[0] - 3.0) < 1e-5
        assert abs(vec[1] - 6.0) < 1e-5
        assert abs(vec[2] - 9.0) < 1e-5

    def test_3d_output_masked_mean_pooling(self):
        """Test mean pooling respects the attention mask."""
        provider = LocalOnnxProvider(dimension=3, do_normalize=False)
        mock_session = MagicMock()
        # Shape (1, 3, 3) - batch=1, seq_len=3, dim=3
        # Third token should be masked out
        mock_session.run.return_value = [
            np.array([[[2.0, 4.0, 6.0], [4.0, 8.0, 12.0], [100.0, 100.0, 100.0]]])
        ]
        provider._session = mock_session
        provider._tokenizer = None

        # Mask: only first 2 of 3 tokens are active
        provider._tokenize = lambda texts: {
            "input_ids": np.zeros((len(texts), 3), dtype=np.int64),
            "attention_mask": np.array([[1, 1, 0]], dtype=np.int64),
        }

        result = provider._embed_sync(["test"])
        vec = result.vectors[0]
        # Mean of [2,4,6] and [4,8,12] only (third is masked) = [3,6,9]
        assert abs(vec[0] - 3.0) < 1e-5
        assert abs(vec[1] - 6.0) < 1e-5
        assert abs(vec[2] - 9.0) < 1e-5

    def test_estimate_tokens(self):
        provider = LocalOnnxProvider()
        assert provider.estimate_tokens("hello world") == 2  # 11 chars // 4
        assert provider.estimate_tokens("hi") == 1  # min 1

    def test_token_count_in_result(self):
        provider = LocalOnnxProvider(dimension=4, do_normalize=False)
        mock_session = MagicMock()
        mock_session.run.return_value = [np.array([[1.0, 2.0, 3.0, 4.0]])]
        provider._session = mock_session
        provider._tokenizer = None

        result = provider._embed_sync(["hello"])
        assert result.token_count > 0
        assert result.model == "nomic-embed-text-v1.5"

    def test_resolve_model_path_nonexistent(self):
        provider = LocalOnnxProvider(model_path="/does/not/exist.onnx")
        assert provider._resolve_model_path() is None

    def test_resolve_model_path_no_path_set(self):
        provider = LocalOnnxProvider()
        # Will return None since model files don't exist in test env
        result = provider._resolve_model_path()
        assert result is None


class TestBaseUtilities:
    """Tests for base module utilities."""

    def test_normalize_l2(self):
        vec = [3.0, 4.0]
        normed = normalize_l2(vec)
        assert abs(normed[0] - 0.6) < 1e-5
        assert abs(normed[1] - 0.8) < 1e-5

    def test_normalize_l2_zero_vector(self):
        vec = [0.0, 0.0, 0.0]
        normed = normalize_l2(vec)
        assert normed == [0.0, 0.0, 0.0]

    def test_normalize_l2_unit_vector(self):
        vec = [1.0, 0.0, 0.0]
        normed = normalize_l2(vec)
        assert abs(normed[0] - 1.0) < 1e-5

    def test_pack_batches_single_batch(self):
        from codegraph.infrastructure.embeddings.base import pack_batches
        batches = pack_batches(["a", "b", "c"], max_batch_size=10)
        assert batches == [[0, 1, 2]]

    def test_pack_batches_multiple_batches(self):
        from codegraph.infrastructure.embeddings.base import pack_batches
        batches = pack_batches(["a", "b", "c", "d", "e"], max_batch_size=2)
        assert batches == [[0, 1], [2, 3], [4]]

    def test_pack_batches_empty(self):
        from codegraph.infrastructure.embeddings.base import pack_batches
        batches = pack_batches([], max_batch_size=10)
        assert batches == []
