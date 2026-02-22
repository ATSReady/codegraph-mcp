"""Code chunking for embedding preparation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from codegraph.domain.models import Symbol, Chunk, SymbolKind


@dataclass
class ChunkingConfig:
    max_chunk_lines: int = 120
    large_class_threshold: int = 120
    sliding_window_size: int = 50
    sliding_window_overlap: int = 10


class CodeChunker:
    """Chunks source code for embedding, using symbol boundaries when available."""

    def __init__(self, config: Optional[ChunkingConfig] = None) -> None:
        self._config = config or ChunkingConfig()

    def chunk_file(
        self,
        file_path: str,
        source_code: str,
        symbols: list[Symbol],
        index_generation: int = 0,
    ) -> list[Chunk]:
        """Chunk a file using symbol boundaries with sliding window fallback."""
        lines = source_code.splitlines(keepends=True)
        if not lines:
            return []

        chunks: list[Chunk] = []
        covered_lines: set[int] = set()

        # Sort symbols by start_line
        sorted_symbols = sorted(symbols, key=lambda s: s.start_line)

        # Process classes first (they may contain methods)
        classes = [s for s in sorted_symbols if s.kind == SymbolKind.CLASS]
        methods = [s for s in sorted_symbols if s.kind == SymbolKind.METHOD]
        functions = [s for s in sorted_symbols if s.kind == SymbolKind.FUNCTION]
        other_symbols = [s for s in sorted_symbols if s.kind not in (
            SymbolKind.CLASS, SymbolKind.METHOD, SymbolKind.FUNCTION,
        )]

        # Chunk classes
        for cls in classes:
            cls_methods = [m for m in methods if m.container_name == cls.name]
            cls_lines = cls.end_line - cls.start_line + 1

            if cls_lines > self._config.large_class_threshold and cls_methods:
                # Large class: chunk per method
                for method in cls_methods:
                    chunk = self._make_symbol_chunk(
                        file_path, lines, method, index_generation,
                        parent_symbol=cls,
                        symbol_ids=[cls.symbol_id, method.symbol_id],
                    )
                    chunks.append(chunk)
                    for ln in range(method.start_line, method.end_line + 1):
                        covered_lines.add(ln)
            else:
                # Small class: one chunk for the whole class
                chunk = self._make_symbol_chunk(
                    file_path, lines, cls, index_generation,
                    symbol_ids=[cls.symbol_id] + [m.symbol_id for m in cls_methods],
                )
                chunks.append(chunk)

            for ln in range(cls.start_line, cls.end_line + 1):
                covered_lines.add(ln)

        # Chunk standalone functions
        for func in functions:
            if func.start_line not in covered_lines:
                chunk = self._make_symbol_chunk(
                    file_path, lines, func, index_generation,
                    symbol_ids=[func.symbol_id],
                )
                chunks.append(chunk)
                for ln in range(func.start_line, func.end_line + 1):
                    covered_lines.add(ln)

        # Chunk other symbols (interfaces, enums, type aliases, etc.)
        for sym in other_symbols:
            if sym.start_line not in covered_lines:
                chunk = self._make_symbol_chunk(
                    file_path, lines, sym, index_generation,
                    symbol_ids=[sym.symbol_id],
                )
                chunks.append(chunk)
                for ln in range(sym.start_line, sym.end_line + 1):
                    covered_lines.add(ln)

        # Sliding window for uncovered regions
        uncovered_chunks = self._chunk_uncovered_lines(
            file_path, lines, covered_lines, index_generation,
        )
        chunks.extend(uncovered_chunks)

        return sorted(chunks, key=lambda c: c.start_line)

    def _make_symbol_chunk(
        self,
        file_path: str,
        lines: list[str],
        symbol: Symbol,
        index_generation: int,
        parent_symbol: Optional[Symbol] = None,
        symbol_ids: Optional[list[str]] = None,
    ) -> Chunk:
        start = symbol.start_line
        end = min(symbol.end_line, len(lines))
        content = "".join(lines[start - 1 : end])

        # Build embedding text with context header
        header_parts = [f"File: {file_path}"]
        if parent_symbol:
            header_parts.append(f"Class: {parent_symbol.name}")
        header_parts.append(f"Symbol: {symbol.symbol_key} ({symbol.kind.value})")
        if symbol.signature:
            header_parts.append(f"Signature: {symbol.signature}")
        if symbol.docstring:
            header_parts.append(f"Docstring: {symbol.docstring}")

        embedding_text = "\n".join(header_parts) + "\n\n" + content

        return Chunk(
            file_path=file_path,
            start_line=start,
            end_line=end,
            content=content,
            embedding_text=embedding_text,
            symbol_ids=symbol_ids or [],
            is_symbol_chunk=True,
            index_generation=index_generation,
        )

    def _chunk_uncovered_lines(
        self,
        file_path: str,
        lines: list[str],
        covered_lines: set[int],
        index_generation: int,
    ) -> list[Chunk]:
        """Apply sliding window to regions not covered by symbol chunks."""
        chunks: list[Chunk] = []
        total = len(lines)

        # Find contiguous uncovered regions
        regions: list[tuple[int, int]] = []
        start = None
        for i in range(1, total + 1):
            if i not in covered_lines:
                if start is None:
                    start = i
            else:
                if start is not None:
                    regions.append((start, i - 1))
                    start = None
        if start is not None:
            regions.append((start, total))

        window = self._config.sliding_window_size
        overlap = self._config.sliding_window_overlap
        step = window - overlap

        for region_start, region_end in regions:
            region_lines = region_end - region_start + 1
            if region_lines <= 0:
                continue

            # Skip very short regions (just whitespace/blank lines)
            region_content = "".join(lines[region_start - 1 : region_end])
            if not region_content.strip():
                continue

            if region_lines <= window:
                # Small region: one chunk
                content = "".join(lines[region_start - 1 : region_end])
                embedding_text = f"File: {file_path}\n\n{content}"
                chunks.append(Chunk(
                    file_path=file_path,
                    start_line=region_start,
                    end_line=region_end,
                    content=content,
                    embedding_text=embedding_text,
                    symbol_ids=[],
                    is_symbol_chunk=False,
                    index_generation=index_generation,
                ))
            else:
                # Sliding window
                pos = region_start
                while pos <= region_end:
                    chunk_end = min(pos + window - 1, region_end)
                    content = "".join(lines[pos - 1 : chunk_end])
                    embedding_text = f"File: {file_path}\n\n{content}"
                    chunks.append(Chunk(
                        file_path=file_path,
                        start_line=pos,
                        end_line=chunk_end,
                        content=content,
                        embedding_text=embedding_text,
                        symbol_ids=[],
                        is_symbol_chunk=False,
                        index_generation=index_generation,
                    ))
                    pos += step
                    if pos > region_end and pos - step + window - 1 < region_end:
                        break

        return chunks

    def build_embedding_text(self, chunk: Chunk) -> str:
        """Return the embedding text for a chunk."""
        return chunk.embedding_text or chunk.content
