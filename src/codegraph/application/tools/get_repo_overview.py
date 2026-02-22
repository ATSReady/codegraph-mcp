"""Get repository index overview."""

from __future__ import annotations

from typing import Optional

from codegraph.domain.ports import SymbolStore, GitClient


class GetRepoOverviewUseCase:
    """Return a high-level overview of the indexed repository state."""

    def __init__(
        self,
        store: SymbolStore,
        git_client: Optional[GitClient] = None,
    ) -> None:
        self._store = store
        self._git = git_client

    def execute(self) -> dict:
        metadata = self._store.get_metadata()
        result: dict = {
            "indexed": metadata is not None,
        }
        if metadata:
            result.update({
                "generation": metadata.generation,
                "head_commit": metadata.workspace_state.head_commit,
                "file_count": len(metadata.file_manifest),
                "embedding_provider": metadata.embedding.provider_id,
                "embedding_model": metadata.embedding.model,
            })
        if self._git:
            result["is_dirty"] = self._git.is_dirty()
            result["current_head"] = self._git.get_head_commit()
        return result
