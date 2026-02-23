"""LanceDB-backed storage adapter implementing SymbolStore protocol."""

from __future__ import annotations

import base64
import json
import warnings
from typing import Optional

import lancedb

from codegraph.domain.models import Symbol, Edge, Chunk, SymbolKind, EdgeKind
from codegraph.domain.workspace import (
    WorkspaceState,
    IndexMetadata,
    EmbeddingMetadata,
    FileManifestEntry,
    FileDiagnostic,
    ParseStatus,
    PackageRoot,
    RepoStats,
)

STORE_SCHEMA_VERSION = 1


class LanceDBStore:
    """SymbolStore implementation backed by LanceDB.

    Each entity type is stored in its own LanceDB table. Domain objects
    are serialized to flat dicts on write and deserialized back on read.
    Upserts are implemented as delete-by-key then add (LanceDB has no
    native upsert). Pagination uses offset-based cursors encoded as
    base64 JSON.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db = lancedb.connect(db_path)

    def _table_exists(self, name: str) -> bool:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return name in self._db.table_names()

    def reset_index_tables(self) -> None:
        """Drop data tables used by full index so re-index starts clean."""
        for name in ("symbols", "edges", "chunks", "diagnostics"):
            if not self._table_exists(name):
                continue
            try:
                self._db.drop_table(name)
            except Exception:
                # Keep indexing resilient even if drop is not supported by backend version.
                pass

    # ------------------------------------------------------------------
    # Symbols
    # ------------------------------------------------------------------

    @staticmethod
    def _symbol_to_row(s: Symbol) -> dict:
        return {
            "symbol_id": s.symbol_id,
            "symbol_key": s.symbol_key,
            "symbol_key_exact": s.symbol_key_exact,
            "name": s.name,
            "kind": s.kind.value,
            "file_path": s.file_path,
            "start_line": s.start_line,
            "end_line": s.end_line,
            "signature": s.signature,
            "language": s.language,
            "module_path": s.module_path or "",
            "container_symbol_id": s.container_symbol_id or "",
            "container_name": s.container_name or "",
            "docstring": s.docstring or "",
            "index_generation": s.index_generation,
            "indexed_at": s.indexed_at or "",
        }

    @staticmethod
    def _row_to_symbol(row: dict) -> Symbol:
        return Symbol(
            name=row["name"],
            kind=SymbolKind(row["kind"]),
            file_path=row["file_path"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            signature=row["signature"],
            language=row["language"],
            module_path=row.get("module_path", ""),
            container_symbol_id=row.get("container_symbol_id") or None,
            container_name=row.get("container_name") or None,
            docstring=row.get("docstring") or None,
            index_generation=row.get("index_generation", 0),
            indexed_at=row.get("indexed_at") or None,
        )

    def get_symbol(self, symbol_id: str) -> Optional[Symbol]:
        if not self._table_exists("symbols"):
            return None
        table = self._db.open_table("symbols")
        results = (
            table.search()
            .where(f"symbol_id = '{_escape(symbol_id)}'")
            .limit(1)
            .to_list()
        )
        if not results:
            return None
        return self._row_to_symbol(results[0])

    def get_symbol_by_key(self, symbol_key: str) -> Optional[Symbol]:
        if not self._table_exists("symbols"):
            return None
        table = self._db.open_table("symbols")
        results = (
            table.search()
            .where(f"symbol_key = '{_escape(symbol_key)}'")
            .limit(1)
            .to_list()
        )
        if not results:
            return None
        return self._row_to_symbol(results[0])

    def query_symbols(
        self,
        file_path: Optional[str] = None,
        kind: Optional[SymbolKind] = None,
        name_pattern: Optional[str] = None,
        max_results: int = 200,
        cursor: Optional[str] = None,
    ) -> tuple[list[Symbol], Optional[str]]:
        if not self._table_exists("symbols"):
            return [], None

        table = self._db.open_table("symbols")
        where = _build_where(
            file_path=file_path,
            kind=kind.value if kind else None,
            name_pattern=name_pattern,
        )

        offset = _decode_cursor(cursor) if cursor else 0

        query = table.search()
        if where:
            query = query.where(where)

        # Fetch offset + max_results + 1 so we can tell whether a next page exists.
        all_results = query.limit(offset + max_results + 1).to_list()
        page = all_results[offset : offset + max_results]

        next_cursor = None
        if len(all_results) > offset + max_results:
            next_cursor = _encode_cursor(offset + max_results)

        return [self._row_to_symbol(r) for r in page], next_cursor

    def upsert_symbols(self, symbols: list[Symbol]) -> None:
        if not symbols:
            return
        rows = [self._symbol_to_row(s) for s in symbols]
        if not self._table_exists("symbols"):
            self._db.create_table("symbols", rows)
        else:
            table = self._db.open_table("symbols")
            for s in symbols:
                try:
                    table.delete(f"symbol_id = '{_escape(s.symbol_id)}'")
                except Exception:
                    pass
            table.add(rows)

    def delete_symbols_by_file(self, file_path: str) -> None:
        if not self._table_exists("symbols"):
            return
        table = self._db.open_table("symbols")
        try:
            table.delete(f"file_path = '{_escape(file_path)}'")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    @staticmethod
    def _edge_to_row(e: Edge) -> dict:
        return {
            "edge_id": e.edge_id,
            "source_symbol_id": e.source_symbol_id,
            "target_symbol_id": e.target_symbol_id or "",
            "kind": e.kind.value,
            "file_path": e.file_path,
            "start_line": e.start_line,
            "end_line": e.end_line,
            "column": e.column,
            "ref_text": e.ref_text,
            "resolution_confidence": e.resolution_confidence,
            "resolution_method": e.resolution_method or "",
            "resolver_id": e.resolver_id or "",
            "resolved_at_generation": e.resolved_at_generation or 0,
            "index_generation": e.index_generation,
            "indexed_at": e.indexed_at or "",
        }

    @staticmethod
    def _row_to_edge(row: dict) -> Edge:
        return Edge(
            source_symbol_id=row["source_symbol_id"],
            target_symbol_id=row.get("target_symbol_id") or None,
            kind=EdgeKind(row["kind"]),
            file_path=row["file_path"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            column=row["column"],
            ref_text=row["ref_text"],
            resolution_confidence=row.get("resolution_confidence", 0.0),
            resolution_method=row.get("resolution_method") or None,
            resolver_id=row.get("resolver_id") or None,
            resolved_at_generation=row.get("resolved_at_generation") or None,
            index_generation=row.get("index_generation", 0),
            indexed_at=row.get("indexed_at") or None,
        )

    def get_edges(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        kind: Optional[EdgeKind] = None,
        file_path: Optional[str] = None,
        max_results: int = 200,
        cursor: Optional[str] = None,
    ) -> tuple[list[Edge], Optional[str]]:
        if not self._table_exists("edges"):
            return [], None

        table = self._db.open_table("edges")
        filters: list[str] = []
        if source_id:
            filters.append(f"source_symbol_id = '{_escape(source_id)}'")
        if target_id:
            filters.append(f"target_symbol_id = '{_escape(target_id)}'")
        if kind:
            filters.append(f"kind = '{_escape(kind.value)}'")
        if file_path:
            filters.append(f"file_path = '{_escape(file_path)}'")

        offset = _decode_cursor(cursor) if cursor else 0
        where = " AND ".join(filters) if filters else None

        query = table.search()
        if where:
            query = query.where(where)

        all_results = query.limit(offset + max_results + 1).to_list()
        page = all_results[offset : offset + max_results]

        next_cursor = None
        if len(all_results) > offset + max_results:
            next_cursor = _encode_cursor(offset + max_results)

        return [self._row_to_edge(r) for r in page], next_cursor

    def upsert_edges(self, edges: list[Edge]) -> None:
        if not edges:
            return
        rows = [self._edge_to_row(e) for e in edges]
        if not self._table_exists("edges"):
            self._db.create_table("edges", rows)
        else:
            table = self._db.open_table("edges")
            for e in edges:
                try:
                    table.delete(f"edge_id = '{_escape(e.edge_id)}'")
                except Exception:
                    pass
            table.add(rows)

    def delete_edges_by_file(self, file_path: str) -> None:
        if not self._table_exists("edges"):
            return
        table = self._db.open_table("edges")
        try:
            table.delete(f"file_path = '{_escape(file_path)}'")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_to_row(c: Chunk) -> dict:
        return {
            "chunk_id": c.chunk_id,
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "content": c.content,
            "symbol_ids": json.dumps(c.symbol_ids),
            "symbol_key_exact": c.symbol_key_exact or "",
            "is_symbol_chunk": c.is_symbol_chunk,
            "language": c.language or "",
            "has_vector": c.has_vector,
            "embedded_hash8": c.embedded_hash8 or "",
            "vector_updated_at": c.vector_updated_at or "",
            "was_truncated": c.was_truncated,
            "content_hash": c.content_hash,
            "content_hash8": c.content_hash8,
            "content_length_chars": c.content_length_chars,
            "content_lines": c.content_lines,
            "index_generation": c.index_generation,
            "indexed_at": c.indexed_at or "",
        }

    @staticmethod
    def _row_to_chunk(row: dict) -> Chunk:
        symbol_ids_raw = row.get("symbol_ids", "[]")
        if isinstance(symbol_ids_raw, str):
            symbol_ids = json.loads(symbol_ids_raw)
        else:
            symbol_ids = list(symbol_ids_raw)

        return Chunk(
            file_path=row["file_path"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            content=row["content"],
            symbol_ids=symbol_ids,
            is_symbol_chunk=row["is_symbol_chunk"],
            symbol_key_exact=row.get("symbol_key_exact") or None,
            language=row.get("language") or None,
            has_vector=row.get("has_vector", False),
            embedded_hash8=row.get("embedded_hash8") or None,
            vector_updated_at=row.get("vector_updated_at") or None,
            was_truncated=row.get("was_truncated", False),
            index_generation=row.get("index_generation", 0),
            indexed_at=row.get("indexed_at") or None,
        )

    def get_chunks(
        self,
        file_path: Optional[str] = None,
        has_vector: Optional[bool] = None,
        max_results: int = 200,
    ) -> list[Chunk]:
        if not self._table_exists("chunks"):
            return []

        table = self._db.open_table("chunks")
        filters: list[str] = []
        if file_path:
            filters.append(f"file_path = '{_escape(file_path)}'")
        if has_vector is not None:
            filters.append(f"has_vector = {str(has_vector).lower()}")

        where = " AND ".join(filters) if filters else None
        query = table.search()
        if where:
            query = query.where(where)

        results = query.limit(max_results).to_list()
        return [self._row_to_chunk(r) for r in results]

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        rows = [self._chunk_to_row(c) for c in chunks]
        if not self._table_exists("chunks"):
            self._db.create_table("chunks", rows)
        else:
            table = self._db.open_table("chunks")
            for c in chunks:
                try:
                    table.delete(f"chunk_id = '{_escape(c.chunk_id)}'")
                except Exception:
                    pass
            table.add(rows)

    def delete_chunks_by_file(self, file_path: str) -> None:
        if not self._table_exists("chunks"):
            return
        table = self._db.open_table("chunks")
        try:
            table.delete(f"file_path = '{_escape(file_path)}'")
        except Exception:
            pass

    def vector_search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        path_prefix: Optional[str] = None,
        language: Optional[str] = None,
        symbol_kind: Optional[str] = None,
        exclude_tests: bool = False,
        file_filter: Optional[str] = None,
    ) -> list[Chunk]:
        if not self._table_exists("chunks"):
            return []

        table = self._db.open_table("chunks")
        filters: list[str] = []
        if path_prefix:
            filters.append(f"file_path LIKE '{_escape(path_prefix)}%'")
        if language:
            filters.append(f"language = '{_escape(language)}'")
        if exclude_tests:
            filters.append("file_path NOT LIKE '%test%'")

        # Vector search requires a vector column — return empty if not available.
        try:
            query = table.search(query_vector)
            if filters:
                query = query.where(" AND ".join(filters))
            results = query.limit(top_k).to_list()
            return [self._row_to_chunk(r) for r in results]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_metadata(self) -> Optional[IndexMetadata]:
        if not self._table_exists("_metadata"):
            return None
        table = self._db.open_table("_metadata")
        results = table.search().limit(1).to_list()
        if not results:
            return None
        data = json.loads(results[0]["data"])
        return _deserialize_metadata(data)

    def set_metadata(self, metadata: IndexMetadata) -> None:
        data = _serialize_metadata(metadata)
        row = {"key": "index_metadata", "data": json.dumps(data)}
        if not self._table_exists("_metadata"):
            self._db.create_table("_metadata", [row])
        else:
            table = self._db.open_table("_metadata")
            try:
                table.delete("key = 'index_metadata'")
            except Exception:
                pass
            table.add([row])

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self) -> list[FileDiagnostic]:
        if not self._table_exists("_diagnostics"):
            return []
        table = self._db.open_table("_diagnostics")
        results = table.search().limit(10000).to_list()
        return [
            FileDiagnostic(
                file_path=r["file_path"],
                parse_status=ParseStatus(r["parse_status"]),
                error_count=r["error_count"],
                error_spans=json.loads(r.get("error_spans", "[]")),
                indexed_at=r.get("indexed_at") or None,
            )
            for r in results
        ]

    def set_diagnostics(self, diagnostics: list[FileDiagnostic]) -> None:
        if not diagnostics:
            return
        rows = [
            {
                "file_path": d.file_path,
                "parse_status": d.parse_status.value,
                "error_count": d.error_count,
                "error_spans": json.dumps(d.error_spans),
                "indexed_at": d.indexed_at or "",
            }
            for d in diagnostics
        ]
        if not self._table_exists("_diagnostics"):
            self._db.create_table("_diagnostics", rows)
        else:
            table = self._db.open_table("_diagnostics")
            try:
                table.delete("file_path IS NOT NULL")
            except Exception:
                pass
            table.add(rows)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def compact(self, keep_generations: int = 3) -> dict:
        """LanceDB handles compaction internally."""
        return {"status": "ok"}

    def close(self) -> None:
        """LanceDB connections don't require explicit closing."""
        pass


# ======================================================================
# Helpers
# ======================================================================


def _escape(value: str) -> str:
    """Escape single quotes for SQL WHERE clauses."""
    return value.replace("'", "''")


def _build_where(
    file_path: Optional[str] = None,
    kind: Optional[str] = None,
    name_pattern: Optional[str] = None,
) -> Optional[str]:
    filters: list[str] = []
    if file_path:
        filters.append(f"file_path = '{_escape(file_path)}'")
    if kind:
        filters.append(f"kind = '{_escape(kind)}'")
    if name_pattern:
        filters.append(f"name LIKE '{_escape(name_pattern)}'")
    return " AND ".join(filters) if filters else None


def _encode_cursor(offset: int) -> str:
    return base64.b64encode(json.dumps({"offset": offset}).encode()).decode()


def _decode_cursor(cursor: str) -> int:
    try:
        data = json.loads(base64.b64decode(cursor))
        return data.get("offset", 0)
    except Exception:
        return 0


def _serialize_metadata(meta: IndexMetadata) -> dict:
    ws = meta.workspace_state
    emb = meta.embedding
    return {
        "schema_version": STORE_SCHEMA_VERSION,
        "generation": meta.generation,
        "workspace_state": {
            "head_commit": ws.head_commit,
            "index_base": ws.index_base,
            "worktree_dirty": ws.worktree_dirty,
            "worktree_fingerprint": ws.worktree_fingerprint,
            "index_timestamp": ws.index_timestamp,
        },
        "embedding": {
            "provider_id": emb.provider_id,
            "model": emb.model,
            "model_revision": emb.model_revision,
            "runtime": emb.runtime,
            "device": emb.device,
            "actual_dimension": emb.actual_dimension,
            "requested_dimension": emb.requested_dimension,
            "config_hash": emb.config_hash,
            "input_version": emb.input_version,
            "normalize": emb.normalize,
        },
        "package_roots": [
            {"language": pr.language, "root_path": pr.root_path, "rule": pr.rule}
            for pr in meta.package_roots
        ],
        "file_manifest": {
            fp: {
                "file_path": entry.file_path,
                "language": entry.language,
                "mtime": entry.mtime,
                "size": entry.size,
                "parse_status": entry.parse_status.value,
            }
            for fp, entry in meta.file_manifest.items()
        },
        "repo_stats": {
            "total_files": meta.repo_stats.total_files,
            "total_bytes": meta.repo_stats.total_bytes,
            "total_tokens": meta.repo_stats.total_tokens,
            "median_file_tokens": meta.repo_stats.median_file_tokens,
            "p75_file_tokens": meta.repo_stats.p75_file_tokens,
            "p90_file_tokens": meta.repo_stats.p90_file_tokens,
            "per_file_tokens": meta.repo_stats.per_file_tokens,
        } if meta.repo_stats else None,
    }


def _deserialize_metadata(data: dict) -> IndexMetadata:
    ws_data = data["workspace_state"]
    emb_data = data["embedding"]

    rs_data = data.get("repo_stats")
    repo_stats = RepoStats(**rs_data) if rs_data else None

    return IndexMetadata(
        workspace_state=WorkspaceState(
            head_commit=ws_data["head_commit"],
            index_base=ws_data["index_base"],
            worktree_dirty=ws_data["worktree_dirty"],
            worktree_fingerprint=ws_data.get("worktree_fingerprint"),
            index_timestamp=ws_data.get("index_timestamp"),
        ),
        embedding=EmbeddingMetadata(
            provider_id=emb_data["provider_id"],
            model=emb_data["model"],
            model_revision=emb_data.get("model_revision"),
            runtime=emb_data["runtime"],
            device=emb_data["device"],
            actual_dimension=emb_data["actual_dimension"],
            requested_dimension=emb_data.get("requested_dimension"),
            config_hash=emb_data["config_hash"],
            input_version=emb_data["input_version"],
            normalize=emb_data["normalize"],
        ),
        generation=data["generation"],
        package_roots=[
            PackageRoot(**pr) for pr in data.get("package_roots", [])
        ],
        file_manifest={
            fp: FileManifestEntry(
                file_path=d["file_path"],
                language=d["language"],
                mtime=d["mtime"],
                size=d["size"],
                parse_status=ParseStatus(d["parse_status"]),
            )
            for fp, d in data.get("file_manifest", {}).items()
        },
        repo_stats=repo_stats,
    )
