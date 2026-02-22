import json
import pytest
from codegraph.infrastructure.parsers.resolvers.typescript_resolver import (
    TypeScriptImportResolver,
    ResolvedImport,
)


@pytest.fixture
def ts_repo(tmp_path):
    """Create a mock TypeScript project structure."""
    # src/components/Button.tsx
    (tmp_path / "src" / "components").mkdir(parents=True)
    (tmp_path / "src" / "components" / "Button.tsx").write_text("export const Button = () => {};\n")
    # src/components/index.ts
    (tmp_path / "src" / "components" / "index.ts").write_text("export * from './Button';\n")
    # src/utils/helpers.ts
    (tmp_path / "src" / "utils").mkdir(parents=True)
    (tmp_path / "src" / "utils" / "helpers.ts").write_text("export function help() {}\n")
    # src/api/client.ts
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "client.ts").write_text("export class ApiClient {}\n")
    # tsconfig.json with paths
    tsconfig = {
        "compilerOptions": {
            "baseUrl": ".",
            "paths": {
                "@/*": ["src/*"],
                "@components/*": ["src/components/*"],
            }
        }
    }
    (tmp_path / "tsconfig.json").write_text(json.dumps(tsconfig))
    return tmp_path


class TestTypeScriptImportResolver:
    def test_resolve_relative_import(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        result = resolver.resolve_import(
            module_string="./helpers",
            source_file="src/utils/client.ts",
        )
        assert result.resolved_path is not None
        assert "helpers.ts" in result.resolved_path
        assert result.is_relative

    def test_resolve_relative_parent(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        result = resolver.resolve_import(
            module_string="../utils/helpers",
            source_file="src/components/Button.tsx",
        )
        assert result.resolved_path is not None
        assert "helpers.ts" in result.resolved_path

    def test_resolve_relative_index(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        result = resolver.resolve_import(
            module_string="./components",
            source_file="src/app.ts",
        )
        assert result.resolved_path is not None
        assert "index.ts" in result.resolved_path

    def test_resolve_path_alias(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        result = resolver.resolve_import(
            module_string="@/utils/helpers",
            source_file="src/components/Button.tsx",
        )
        assert result.resolved_path is not None
        assert "helpers.ts" in result.resolved_path

    def test_resolve_component_alias(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        result = resolver.resolve_import(
            module_string="@components/Button",
            source_file="src/api/client.ts",
        )
        assert result.resolved_path is not None
        assert "Button.tsx" in result.resolved_path

    def test_bare_specifier_is_external(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        result = resolver.resolve_import(
            module_string="express",
            source_file="src/api/client.ts",
        )
        assert result.is_external
        assert result.resolved_path is None

    def test_node_modules_external(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        result = resolver.resolve_import(
            module_string="@types/node",
            source_file="src/api/client.ts",
        )
        assert result.is_external

    def test_resolve_file_imports_batch(self, ts_repo):
        resolver = TypeScriptImportResolver(str(ts_repo))
        imports = [
            {"module_string": "express"},
            {"module_string": "./helpers", "imported_names": ["help"]},
        ]
        results = resolver.resolve_file_imports("src/utils/client.ts", imports)
        assert len(results) == 2
        assert results[0].is_external
        assert results[1].resolved_path is not None

    def test_tsconfig_with_comments(self, tmp_path):
        """tsconfig.json with JS-style comments should parse."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("const x = 1;\n")
        tsconfig = '''
        {
            // This is a comment
            "compilerOptions": {
                "baseUrl": ".",
                /* Another comment */
                "paths": {
                    "@/*": ["src/*"]
                }
            }
        }
        '''
        (tmp_path / "tsconfig.json").write_text(tsconfig)
        resolver = TypeScriptImportResolver(str(tmp_path))
        result = resolver.resolve_import("@/app", source_file="test.ts")
        assert result.resolved_path is not None
