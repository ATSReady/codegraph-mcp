import pytest
from codegraph.infrastructure.embeddings.base import (
    normalize_l2, estimate_tokens, pack_batches, EmbeddingResult,
)
from codegraph.infrastructure.embeddings.factory import ProviderFactory
from codegraph.domain.config import EmbeddingConfig
from codegraph.domain.errors import ProviderUnavailableError


class TestNormalizeL2:
    def test_unit_vector(self):
        v = normalize_l2([3.0, 4.0])
        norm = sum(x * x for x in v) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_zero_vector(self):
        v = normalize_l2([0.0, 0.0])
        assert v == [0.0, 0.0]

    def test_already_normalized(self):
        v = normalize_l2([1.0, 0.0])
        assert abs(v[0] - 1.0) < 1e-6
        assert abs(v[1] - 0.0) < 1e-6


class TestEstimateTokens:
    def test_basic_estimation(self):
        # 100 chars / 4.0 = 25 tokens
        assert estimate_tokens("a" * 100) == 25

    def test_min_one(self):
        assert estimate_tokens("") == 1

    def test_custom_ratio(self):
        assert estimate_tokens("a" * 100, chars_per_token=2.0) == 50


class TestPackBatches:
    def test_single_batch(self):
        texts = ["hello", "world", "test"]
        batches = pack_batches(texts, max_batch_size=10, max_batch_tokens=10000)
        assert len(batches) == 1
        assert sorted(batches[0]) == [0, 1, 2]

    def test_batch_size_limit(self):
        texts = ["text"] * 10
        batches = pack_batches(texts, max_batch_size=3, max_batch_tokens=100000)
        assert len(batches) >= 4  # ceil(10/3) = 4

    def test_token_limit(self):
        texts = ["a" * 400] * 5  # Each ~100 tokens
        batches = pack_batches(texts, max_batch_size=100, max_batch_tokens=150)
        assert len(batches) >= 2  # Can't fit all in one batch

    def test_empty_input(self):
        batches = pack_batches([])
        assert batches == []


class TestProviderFactory:
    def test_unknown_provider_raises(self):
        config = EmbeddingConfig(provider="nonexistent")
        with pytest.raises(ProviderUnavailableError):
            ProviderFactory.create(config)

    def test_available_providers(self):
        providers = ProviderFactory.available_providers()
        assert "local" in providers
        assert "openai" in providers
        assert "voyage" in providers

    def test_register_custom_provider(self):
        class MockProvider:
            def __init__(self, config):
                self.config = config

        ProviderFactory.register("mock", MockProvider)
        config = EmbeddingConfig(provider="mock")
        provider = ProviderFactory.create(config)
        assert isinstance(provider, MockProvider)
        # Cleanup
        del ProviderFactory._registry["mock"]
