"""Verify port protocols are importable and structurally correct."""
import inspect
from codegraph.domain.ports import (
    SymbolStore, EmbeddingProvider, GitClient,
    FileWatcher, CodeParser, ImportResolver,
)


class TestPortsExist:
    def test_symbol_store_has_required_methods(self):
        methods = [m for m in dir(SymbolStore) if not m.startswith("_")]
        assert "get_symbol" in methods
        assert "query_symbols" in methods
        assert "upsert_symbols" in methods
        assert "delete_symbols_by_file" in methods

    def test_embedding_provider_has_required_attrs(self):
        assert hasattr(EmbeddingProvider, "name")
        assert hasattr(EmbeddingProvider, "dimension")
        assert hasattr(EmbeddingProvider, "embed_batch")
        assert hasattr(EmbeddingProvider, "embed_single")
        assert hasattr(EmbeddingProvider, "estimate_tokens")
        assert hasattr(EmbeddingProvider, "max_batch_tokens")

    def test_git_client_has_required_methods(self):
        methods = [m for m in dir(GitClient) if not m.startswith("_")]
        assert "get_head_commit" in methods
        assert "get_changed_files_since" in methods
        assert "get_untracked_files" in methods

    def test_code_parser_has_required_methods(self):
        methods = [m for m in dir(CodeParser) if not m.startswith("_")]
        assert "parse_file" in methods
        assert "available_languages" in methods

    def test_import_resolver_has_required_methods(self):
        methods = [m for m in dir(ImportResolver) if not m.startswith("_")]
        assert "resolve_imports" in methods
