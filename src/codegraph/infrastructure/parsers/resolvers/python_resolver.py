"""Conservative Python import resolver."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ResolvedImport:
    """Result of resolving a Python import."""
    module_string: str
    imported_names: list[str]
    resolved_path: Optional[str] = None  # Relative to repo root
    is_relative: bool = False
    is_external: bool = False
    candidate_paths: list[str] = field(default_factory=list)


class PythonImportResolver:
    """Resolves Python imports to file paths within a repository."""

    # Common stdlib modules to skip
    STDLIB_MODULES = {
        "abc", "ast", "asyncio", "base64", "builtins", "collections", "concurrent",
        "contextlib", "copy", "csv", "dataclasses", "datetime", "decimal", "enum",
        "errno", "functools", "glob", "hashlib", "http", "importlib", "inspect",
        "io", "itertools", "json", "logging", "math", "multiprocessing", "os",
        "pathlib", "pickle", "platform", "pprint", "queue", "random", "re",
        "shutil", "signal", "socket", "sqlite3", "string", "struct", "subprocess",
        "sys", "tempfile", "textwrap", "threading", "time", "traceback", "typing",
        "unittest", "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
    }

    def __init__(self, repo_root: str, package_roots: Optional[list[str]] = None) -> None:
        self._repo_root = Path(repo_root)
        self._package_roots = package_roots or self._detect_package_roots()

    def _detect_package_roots(self) -> list[str]:
        """Find source root directories containing Python packages."""
        roots = []
        # Check for common source layouts
        for candidate in ["src", "lib", "."]:
            candidate_path = self._repo_root / candidate
            if candidate_path.is_dir():
                # Check if it has Python packages (dirs with __init__.py)
                has_packages = False
                for item in candidate_path.iterdir():
                    if item.is_dir() and (item / "__init__.py").exists():
                        has_packages = True
                        break
                if has_packages:
                    roots.append(candidate)
        if not roots:
            roots.append(".")
        return roots

    def resolve_import(
        self,
        module_string: str,
        imported_names: list[str],
        source_file: str,
        is_relative: bool = False,
        relative_level: int = 0,
    ) -> ResolvedImport:
        """Resolve a single import statement."""
        result = ResolvedImport(
            module_string=module_string,
            imported_names=imported_names,
            is_relative=is_relative,
        )

        if is_relative:
            return self._resolve_relative(result, source_file, relative_level)

        # Check if stdlib
        top_module = module_string.split(".")[0]
        if top_module in self.STDLIB_MODULES:
            result.is_external = True
            return result

        return self._resolve_absolute(result)

    def _resolve_relative(self, result: ResolvedImport, source_file: str, level: int) -> ResolvedImport:
        """Resolve a relative import (from . or from ..)."""
        source_path = Path(source_file)
        # Go up 'level' directories from source file's directory
        base_dir = source_path.parent
        for _ in range(level - 1):
            base_dir = base_dir.parent

        if result.module_string:
            parts = result.module_string.split(".")
            candidate = base_dir / "/".join(parts)
        else:
            candidate = base_dir

        # Check file.py or package/__init__.py
        candidates = self._get_candidates(candidate)
        for c in candidates:
            full = self._repo_root / c
            if full.exists():
                result.resolved_path = str(c)
                return result

        result.candidate_paths = [str(c) for c in candidates]
        return result

    def _resolve_absolute(self, result: ResolvedImport) -> ResolvedImport:
        """Resolve an absolute import against package roots."""
        parts = result.module_string.split(".")
        candidates = []

        for root in self._package_roots:
            candidate = Path(root) / "/".join(parts)
            for c in self._get_candidates(candidate):
                candidates.append(c)
                full = self._repo_root / c
                if full.exists():
                    result.resolved_path = str(c)
                    return result

        if not result.resolved_path:
            # No file matched any candidate — treat as external (third-party)
            result.is_external = True
        return result

    def _get_candidates(self, base: Path) -> list[Path]:
        """Get candidate file paths for a module path."""
        return [
            base.with_suffix(".py"),
            base / "__init__.py",
        ]

    def resolve_file_imports(
        self, source_file: str, imports: list[dict],
    ) -> list[ResolvedImport]:
        """Resolve all imports from a file."""
        results = []
        for imp in imports:
            resolved = self.resolve_import(
                module_string=imp.get("module_string", ""),
                imported_names=imp.get("imported_names", []),
                source_file=source_file,
                is_relative=imp.get("is_relative", False),
                relative_level=imp.get("relative_level", 0),
            )
            results.append(resolved)
        return results
