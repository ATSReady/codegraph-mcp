"""Language detection and tree-sitter grammar loading."""

from __future__ import annotations

from typing import Optional
import warnings

import tree_sitter_languages  # type: ignore[import-untyped]


LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
}


def detect_language(file_path: str) -> Optional[str]:
    """Detect language from file extension.

    Returns the language name or None if unsupported.
    """
    dot_idx = file_path.rfind(".")
    if dot_idx == -1:
        return None
    ext = file_path[dot_idx:]
    return LANGUAGE_EXTENSIONS.get(ext)


def get_grammar(language: str) -> object:
    """Load a tree-sitter grammar for the given language.

    Returns a tree_sitter.Language instance.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Language\(path, name\) is deprecated.*",
            category=FutureWarning,
        )
        return tree_sitter_languages.get_language(language)


def get_parser(language: str) -> object:
    """Load a tree-sitter parser for the given language.

    Returns a tree_sitter.Parser pre-configured with the language grammar.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Language\(path, name\) is deprecated.*",
            category=FutureWarning,
        )
        return tree_sitter_languages.get_parser(language)


def available_languages() -> list[dict]:
    """Return list of supported languages with their extensions.

    Each entry is a dict with ``name`` and ``extensions`` keys.
    """
    grouped: dict[str, list[str]] = {}
    for ext, lang in LANGUAGE_EXTENSIONS.items():
        grouped.setdefault(lang, []).append(ext)
    return [{"name": lang, "extensions": sorted(exts)} for lang, exts in sorted(grouped.items())]
