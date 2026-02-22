import json
import pytest
from unittest.mock import patch, MagicMock
from codegraph.infrastructure.embeddings.openai_provider import OpenAIProvider
from codegraph.infrastructure.embeddings.voyage_provider import VoyageProvider


class TestOpenAIProvider:
    def test_init_defaults(self):
        provider = OpenAIProvider(api_key="test-key")
        assert provider.model_name == "text-embedding-3-small"
        assert provider.dimension == 1536
        assert provider.provider_name == "openai"

    def test_embed_empty(self):
        provider = OpenAIProvider(api_key="test-key")
        result = provider.embed([])
        assert result.vectors == []

    def test_embed_no_api_key_raises(self):
        provider = OpenAIProvider(api_key="")
        with pytest.raises(RuntimeError, match="API key"):
            provider.embed(["test"])

    @patch("codegraph.infrastructure.embeddings.openai_provider.urlopen")
    def test_embed_single_text(self, mock_urlopen):
        response_data = {
            "data": [{"embedding": [0.1, 0.2, 0.3], "index": 0}],
            "usage": {"total_tokens": 5},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = OpenAIProvider(api_key="test-key", dimension=3, normalize=False)
        result = provider.embed(["hello"])
        assert len(result.vectors) == 1
        assert result.vectors[0] == [0.1, 0.2, 0.3]
        assert result.token_count == 5

    @patch("codegraph.infrastructure.embeddings.openai_provider.urlopen")
    def test_embed_with_normalization(self, mock_urlopen):
        response_data = {
            "data": [{"embedding": [3.0, 4.0], "index": 0}],
            "usage": {"total_tokens": 3},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = OpenAIProvider(api_key="test-key", dimension=2, normalize=True)
        result = provider.embed(["test"])
        norm = sum(x * x for x in result.vectors[0]) ** 0.5
        assert abs(norm - 1.0) < 1e-5

    @patch("codegraph.infrastructure.embeddings.openai_provider.urlopen")
    def test_embed_multiple_texts(self, mock_urlopen):
        response_data = {
            "data": [
                {"embedding": [1.0, 0.0], "index": 0},
                {"embedding": [0.0, 1.0], "index": 1},
            ],
            "usage": {"total_tokens": 10},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = OpenAIProvider(api_key="test-key", dimension=2, normalize=False)
        result = provider.embed(["hello", "world"])
        assert len(result.vectors) == 2

    def test_custom_dimension(self):
        provider = OpenAIProvider(api_key="test-key", dimension=256)
        assert provider.dimension == 256

    def test_embed_single(self):
        provider = OpenAIProvider(api_key="test-key", dimension=3, normalize=False)
        with patch.object(provider, "_call_api") as mock_api:
            mock_api.return_value = {
                "data": [{"embedding": [1.0, 2.0, 3.0], "index": 0}],
                "usage": {"total_tokens": 5},
            }
            vec = provider.embed_single("test")
            assert vec == [1.0, 2.0, 3.0]


class TestVoyageProvider:
    def test_init_defaults(self):
        provider = VoyageProvider(api_key="test-key")
        assert provider.model_name == "voyage-code-2"
        assert provider.dimension == 1536
        assert provider.provider_name == "voyage"

    def test_embed_empty(self):
        provider = VoyageProvider(api_key="test-key")
        result = provider.embed([])
        assert result.vectors == []

    def test_embed_no_api_key_raises(self):
        provider = VoyageProvider(api_key="")
        with pytest.raises(RuntimeError, match="API key"):
            provider.embed(["test"])

    @patch("codegraph.infrastructure.embeddings.voyage_provider.urlopen")
    def test_embed_single_text(self, mock_urlopen):
        response_data = {
            "data": [{"embedding": [0.5, 0.5, 0.5]}],
            "usage": {"total_tokens": 4},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = VoyageProvider(api_key="test-key", dimension=3, normalize=False)
        result = provider.embed(["hello"])
        assert len(result.vectors) == 1
        assert result.vectors[0] == [0.5, 0.5, 0.5]

    @patch("codegraph.infrastructure.embeddings.voyage_provider.urlopen")
    def test_embed_multiple(self, mock_urlopen):
        response_data = {
            "data": [
                {"embedding": [1.0, 0.0]},
                {"embedding": [0.0, 1.0]},
            ],
            "usage": {"total_tokens": 8},
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        provider = VoyageProvider(api_key="test-key", dimension=2, normalize=False)
        result = provider.embed(["a", "b"])
        assert len(result.vectors) == 2
        assert result.token_count == 8
