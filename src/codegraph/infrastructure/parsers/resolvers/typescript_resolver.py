"""TypeScript/JavaScript import resolver."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ResolvedImport:
    """Result of resolving a TS/JS import."""
    module_string: str
    imported_names: list[str] = field(default_factory=list)
    resolved_path: Optional[str] = None  # Relative to repo root
    is_relative: bool = False
    is_external: bool = False
    candidate_paths: list[str] = field(default_factory=list)


class TypeScriptImportResolver:
    """Resolves TypeScript/JavaScript imports to file paths."""

    # Extensions to try when resolving
    TS_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".d.ts"]
    JS_EXTENSIONS = [".js", ".jsx", ".ts", ".tsx"]
    INDEX_FILES = ["index.ts", "index.tsx", "index.js", "index.jsx"]

    def __init__(self, repo_root: str, tsconfig_path: Optional[str] = None) -> None:
        self._repo_root = Path(repo_root)
        self._path_aliases: dict[str, list[str]] = {}
        self._base_url: Optional[str] = None
        if tsconfig_path:
            self._load_tsconfig(tsconfig_path)
        else:
            self._try_load_tsconfig()

    def _try_load_tsconfig(self) -> None:
        for name in ["tsconfig.json", "jsconfig.json"]:
            path = self._repo_root / name
            if path.exists():
                self._load_tsconfig(str(path))
                break

    def _load_tsconfig(self, path: str) -> None:
        try:
            # Strip comments from tsconfig (// and /* */ style)
            text = Path(path).read_text()
            text = re.sub(r'//.*$', '', text, flags=re.MULTILINE)
            text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
            config = json.loads(text)
            compiler = config.get("compilerOptions", {})
            self._base_url = compiler.get("baseUrl")
            paths = compiler.get("paths", {})
            for alias, targets in paths.items():
                # Normalize: "@/*" -> "@/"
                self._path_aliases[alias] = targets
        except (json.JSONDecodeError, OSError):
            pass

    def resolve_import(
        self,
        module_string: str,
        imported_names: Optional[list[str]] = None,
        source_file: str = "",
    ) -> ResolvedImport:
        result = ResolvedImport(
            module_string=module_string,
            imported_names=imported_names or [],
        )

        if not module_string:
            return result

        # Relative import
        if module_string.startswith("."):
            result.is_relative = True
            return self._resolve_relative(result, source_file)

        # Check path aliases
        alias_result = self._resolve_alias(result)
        if alias_result and alias_result.resolved_path:
            return alias_result

        # Bare specifier = external (node_modules)
        result.is_external = True
        return result

    def _resolve_relative(self, result: ResolvedImport, source_file: str) -> ResolvedImport:
        source_dir = Path(source_file).parent
        target = source_dir / result.module_string
        # Normalize the path (resolve .. and . segments)
        try:
            target = Path(*target.parts) if target.parts else target
        except TypeError:
            pass

        candidates = self._get_candidates(target)
        for c in candidates:
            full = self._repo_root / c
            if full.exists():
                result.resolved_path = str(c)
                return result

        result.candidate_paths = [str(c) for c in candidates]
        return result

    def _resolve_alias(self, result: ResolvedImport) -> Optional[ResolvedImport]:
        for alias_pattern, targets in self._path_aliases.items():
            # Convert glob pattern to prefix
            prefix = alias_pattern.rstrip("*")
            if result.module_string.startswith(prefix):
                remainder = result.module_string[len(prefix):]
                for target_pattern in targets:
                    target_prefix = target_pattern.rstrip("*")
                    if self._base_url:
                        base = Path(self._base_url) / target_prefix / remainder
                    else:
                        base = Path(target_prefix) / remainder

                    candidates = self._get_candidates(base)
                    for c in candidates:
                        full = self._repo_root / c
                        if full.exists():
                            result.resolved_path = str(c)
                            return result
        return None

    def _get_candidates(self, base: Path) -> list[Path]:
        """Get candidate file paths with various extensions."""
        candidates = []
        # Try direct path with extensions
        for ext in self.TS_EXTENSIONS:
            candidates.append(base.with_suffix(ext))
        # Try index files in directory
        for index in self.INDEX_FILES:
            candidates.append(base / index)
        return candidates

    def resolve_file_imports(
        self, source_file: str, imports: list[dict],
    ) -> list[ResolvedImport]:
        results = []
        for imp in imports:
            resolved = self.resolve_import(
                module_string=imp.get("module_string", ""),
                imported_names=imp.get("imported_names", []),
                source_file=source_file,
            )
            results.append(resolved)
        return results
