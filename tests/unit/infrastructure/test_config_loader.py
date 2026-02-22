import os
import pytest
from codegraph.infrastructure.config_loader import load_config, save_default_config


class TestConfigLoader:
    def test_load_defaults_when_missing(self, tmp_path):
        config = load_config(str(tmp_path))
        assert config.index.exclude is not None
        assert config.server.log_level == "info"
        assert config.embedding.provider == "local"

    def test_load_from_toml(self, tmp_path):
        config_dir = tmp_path / ".codegraph"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("""
[index]
exclude = ["dist/**"]

[server]
log_level = "debug"
auto_reindex = false

[embedding]
provider = "openai"
model = "text-embedding-3-large"
batch_size = 32
""")
        config = load_config(str(tmp_path))
        assert config.index.exclude == ["dist/**"]
        assert config.server.log_level == "debug"
        assert config.server.auto_reindex is False
        assert config.embedding.provider == "openai"
        assert config.embedding.model == "text-embedding-3-large"
        assert config.embedding.batch_size == 32

    def test_load_partial_config(self, tmp_path):
        config_dir = tmp_path / ".codegraph"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text('[server]\nlog_level = "warning"\n')
        config = load_config(str(tmp_path))
        assert config.server.log_level == "warning"
        assert config.embedding.provider == "local"  # Default kept

    def test_load_invalid_toml_returns_defaults(self, tmp_path):
        config_dir = tmp_path / ".codegraph"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text("not valid toml {{{}}")
        config = load_config(str(tmp_path))
        assert config.server.log_level == "info"

    def test_custom_config_path(self, tmp_path):
        custom = tmp_path / "custom.toml"
        custom.write_text('[embedding]\nprovider = "voyage"\n')
        config = load_config(str(tmp_path), config_path=str(custom))
        assert config.embedding.provider == "voyage"

    def test_save_default_config(self, tmp_path):
        config_path = str(tmp_path / ".codegraph" / "config.toml")
        save_default_config(config_path)
        assert os.path.exists(config_path)
        # Verify it's loadable
        config = load_config(str(tmp_path))
        assert config.server.auto_reindex is True
