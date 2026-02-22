"""Typed error hierarchy with stable error codes."""

from __future__ import annotations

from typing import Optional


class CodegraphError(Exception):
    error_code: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "error": self.error_code,
            "message": str(self),
        }


class NoIndexError(CodegraphError):
    error_code = "no_index"

    def __init__(self) -> None:
        super().__init__("No index found. Run 'codegraph index' to build the code graph.")


class ProviderUnavailableError(CodegraphError):
    error_code = "provider_unavailable"

    def __init__(self, provider: str) -> None:
        super().__init__(f"Embedding provider '{provider}' is not available.")


class ProviderMismatchError(CodegraphError):
    error_code = "provider_mismatch"

    def __init__(self, configured: str, indexed: str) -> None:
        super().__init__(
            f"Configured provider '{configured}' differs from indexed provider '{indexed}'. "
            f"Run 'codegraph index' to rebuild."
        )
        self.configured = configured
        self.indexed = indexed


class IndexLockedError(CodegraphError):
    error_code = "index_locked"

    def __init__(self, pid: int, hostname: str) -> None:
        super().__init__(
            f"Index is locked by PID {pid} on {hostname}. "
            f"If stale, remove .codegraph/index.lock or use --break-stale-lock."
        )
        self.pid = pid
        self.hostname = hostname


class InvalidArgsError(CodegraphError):
    error_code = "invalid_args"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class BlockedError(CodegraphError):
    error_code = "blocked"

    def __init__(self, message: str) -> None:
        super().__init__(message)
