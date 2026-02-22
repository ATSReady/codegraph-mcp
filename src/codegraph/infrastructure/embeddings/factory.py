"""Factory for creating embedding providers from configuration."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from codegraph.domain.config import EmbeddingConfig
from codegraph.domain.errors import ProviderUnavailableError

if TYPE_CHECKING:
    from codegraph.domain.ports import EmbeddingProvider


class ProviderFactory:
    """Creates embedding providers based on configuration."""

    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str, provider_class: type) -> None:
        """Register a provider class for a given name."""
        cls._registry[name] = provider_class

    @classmethod
    def create(cls, config: EmbeddingConfig) -> "EmbeddingProvider":
        """Create an embedding provider from config."""
        provider_name = config.provider.lower()
        
        if provider_name == "local":
            return cls._create_local(config)
        elif provider_name in ("openai", "voyage"):
            return cls._create_api(provider_name, config)
        elif provider_name in cls._registry:
            return cls._registry[provider_name](config)
        else:
            raise ProviderUnavailableError(
                provider_name,
                f"Unknown embedding provider: {provider_name}. "
                f"Available: local, openai, voyage, {', '.join(cls._registry.keys())}"
            )

    @classmethod
    def _create_local(cls, config: EmbeddingConfig) -> "EmbeddingProvider":
        try:
            from codegraph.infrastructure.embeddings.local_onnx import LocalOnnxProvider
            return LocalOnnxProvider(
                model_name=config.model or "nomic-embed-text-v1.5",
                dimension=config.dimension,
                normalize=config.normalize_vectors,
            )
        except ImportError as e:
            raise ProviderUnavailableError("local", f"ONNX Runtime not installed: {e}")

    @classmethod
    def _create_api(cls, name: str, config: EmbeddingConfig) -> "EmbeddingProvider":
        import os
        api_key = None
        if config.api_key_env:
            api_key = os.environ.get(config.api_key_env)
        
        if name == "openai":
            try:
                from codegraph.infrastructure.embeddings.openai_provider import OpenAIProvider
                return OpenAIProvider(
                    model=config.model or "text-embedding-3-small",
                    api_key=api_key,
                    dimension=config.dimension,
                    normalize=config.normalize_vectors,
                    batch_size=config.batch_size,
                    max_concurrent=config.max_concurrent_requests,
                )
            except ImportError as e:
                raise ProviderUnavailableError("openai", f"OpenAI dependencies missing: {e}")
        elif name == "voyage":
            try:
                from codegraph.infrastructure.embeddings.voyage_provider import VoyageProvider
                return VoyageProvider(
                    model=config.model or "voyage-code-2",
                    api_key=api_key,
                    dimension=config.dimension,
                    normalize=config.normalize_vectors,
                    batch_size=config.batch_size,
                    max_concurrent=config.max_concurrent_requests,
                )
            except ImportError as e:
                raise ProviderUnavailableError("voyage", f"Voyage dependencies missing: {e}")
        
        raise ProviderUnavailableError(name, f"Unknown API provider: {name}")

    @classmethod 
    def available_providers(cls) -> list[str]:
        """List available provider names."""
        base = ["local", "openai", "voyage"]
        return base + list(cls._registry.keys())
