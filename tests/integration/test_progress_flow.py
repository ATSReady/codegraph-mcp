from __future__ import annotations

import threading
import time
from pathlib import Path

from codegraph.application.index_progress_tracker import IndexProgressTracker
from codegraph.application.index_repo import IndexRepoUseCase
from codegraph.domain.config import CodegraphConfig, IndexConfig
from codegraph.infrastructure.git.client import SubprocessGitClient
from codegraph.infrastructure.parsers.chunker import CodeChunker
from codegraph.infrastructure.parsers.tree_sitter_parser import TreeSitterParser
from codegraph.infrastructure.storage.lancedb_store import LanceDBStore
from codegraph.interface.mcp.server import CodegraphServer


class SlowParser:
    def __init__(self) -> None:
        self._inner = TreeSitterParser()

    def parse_file(self, file_path, content):
        time.sleep(0.05)
        return self._inner.parse_file(file_path, content)


def _init_repo(tmp_path: Path) -> Path:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    (repo / "a.py").write_text("def a():\n    return 1\n")
    (repo / "b.py").write_text("def b():\n    return 2\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True, check=True)
    return repo


def test_progress_visible_while_index_running(tmp_path):
    repo = _init_repo(tmp_path)
    store = LanceDBStore(str(tmp_path / "index.lance"))
    git = SubprocessGitClient(str(repo))
    tracker = IndexProgressTracker()
    use_case = IndexRepoUseCase(
        store=store,
        parser=SlowParser(),
        git_client=git,
        chunker=CodeChunker(),
        progress_tracker=tracker,
        config=CodegraphConfig(index=IndexConfig(parallel_workers=1)),
    )

    done = threading.Event()

    def _run():
        use_case.execute(str(repo))
        done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    server = CodegraphServer(store=store, git_client=git, progress_tracker=tracker)
    seen_running = False
    deadline = time.time() + 5.0
    while time.time() < deadline and not done.is_set():
        payload = server._get_index_progress_result()
        progress = payload.get("progress")
        if progress and progress.get("state") in {"running", "committing"}:
            seen_running = True
            break
        time.sleep(0.02)

    t.join(timeout=10)
    assert seen_running
    final = tracker.get_last()
    assert final is not None
    assert final.state.value == "completed"
    store.close()
