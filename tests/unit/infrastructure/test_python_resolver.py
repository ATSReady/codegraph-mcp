import pytest
from codegraph.infrastructure.parsers.resolvers.python_resolver import (
    PythonImportResolver,
    ResolvedImport,
)


@pytest.fixture
def mock_repo(tmp_path):
    """Create a mock Python project structure."""
    # src/myapp/__init__.py
    (tmp_path / "src" / "myapp").mkdir(parents=True)
    (tmp_path / "src" / "myapp" / "__init__.py").touch()
    # src/myapp/auth/__init__.py
    (tmp_path / "src" / "myapp" / "auth").mkdir()
    (tmp_path / "src" / "myapp" / "auth" / "__init__.py").touch()
    (tmp_path / "src" / "myapp" / "auth" / "middleware.py").write_text("def verify(): pass\n")
    # src/myapp/models.py
    (tmp_path / "src" / "myapp" / "models.py").write_text("class User: pass\n")
    # src/myapp/utils/helpers.py
    (tmp_path / "src" / "myapp" / "utils").mkdir()
    (tmp_path / "src" / "myapp" / "utils" / "__init__.py").touch()
    (tmp_path / "src" / "myapp" / "utils" / "helpers.py").write_text("def help(): pass\n")
    return tmp_path


class TestPythonImportResolver:
    def test_resolve_relative_import(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo), package_roots=["src"])
        result = resolver.resolve_import(
            module_string="models",
            imported_names=["User"],
            source_file="src/myapp/auth/middleware.py",
            is_relative=True,
            relative_level=2,
        )
        assert result.resolved_path is not None
        assert "models.py" in result.resolved_path

    def test_resolve_relative_sibling(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo), package_roots=["src"])
        result = resolver.resolve_import(
            module_string="middleware",
            imported_names=["verify"],
            source_file="src/myapp/auth/__init__.py",
            is_relative=True,
            relative_level=1,
        )
        assert result.resolved_path is not None
        assert "middleware.py" in result.resolved_path

    def test_resolve_absolute_import(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo), package_roots=["src"])
        result = resolver.resolve_import(
            module_string="myapp.auth.middleware",
            imported_names=["verify"],
            source_file="src/myapp/models.py",
        )
        assert result.resolved_path is not None
        assert "middleware.py" in result.resolved_path

    def test_resolve_absolute_package(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo), package_roots=["src"])
        result = resolver.resolve_import(
            module_string="myapp.auth",
            imported_names=["middleware"],
            source_file="src/myapp/models.py",
        )
        assert result.resolved_path is not None
        assert "__init__.py" in result.resolved_path

    def test_stdlib_marked_external(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo), package_roots=["src"])
        result = resolver.resolve_import(
            module_string="os",
            imported_names=["path"],
            source_file="src/myapp/models.py",
        )
        assert result.is_external is True
        assert result.resolved_path is None

    def test_unknown_import_marked_external(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo), package_roots=["src"])
        result = resolver.resolve_import(
            module_string="requests",
            imported_names=["get"],
            source_file="src/myapp/models.py",
        )
        assert result.is_external is True

    def test_detect_package_roots(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo))
        assert "src" in resolver._package_roots

    def test_resolve_file_imports_batch(self, mock_repo):
        resolver = PythonImportResolver(str(mock_repo), package_roots=["src"])
        imports = [
            {"module_string": "os", "imported_names": ["path"]},
            {"module_string": "myapp.models", "imported_names": ["User"]},
        ]
        results = resolver.resolve_file_imports("src/myapp/auth/middleware.py", imports)
        assert len(results) == 2
        assert results[0].is_external  # os
        assert results[1].resolved_path is not None  # myapp.models
