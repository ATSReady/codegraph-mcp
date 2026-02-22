import pytest
from codegraph.infrastructure.parsers.chunker import CodeChunker, ChunkingConfig
from codegraph.domain.models import Symbol, SymbolKind


@pytest.fixture
def chunker():
    return CodeChunker()


@pytest.fixture
def small_class_code():
    return (
        "import os\n"
        "\n"
        "class UserService:\n"
        "    def __init__(self, db):\n"
        "        self.db = db\n"
        "\n"
        "    def get_user(self, id):\n"
        "        return self.db.get(id)\n"
        "\n"
        "    def delete_user(self, id):\n"
        "        self.db.delete(id)\n"
    )


@pytest.fixture
def small_class_symbols():
    return [
        Symbol(
            name="UserService", kind=SymbolKind.CLASS,
            file_path="service.py", start_line=3, end_line=11,
            signature="class UserService", language="python",
        ),
        Symbol(
            name="__init__", kind=SymbolKind.METHOD,
            file_path="service.py", start_line=4, end_line=5,
            signature="def __init__(self, db)", language="python",
            container_name="UserService",
        ),
        Symbol(
            name="get_user", kind=SymbolKind.METHOD,
            file_path="service.py", start_line=7, end_line=8,
            signature="def get_user(self, id)", language="python",
            container_name="UserService",
        ),
        Symbol(
            name="delete_user", kind=SymbolKind.METHOD,
            file_path="service.py", start_line=10, end_line=11,
            signature="def delete_user(self, id)", language="python",
            container_name="UserService",
        ),
    ]


class TestCodeChunker:
    def test_small_class_single_chunk(self, chunker, small_class_code, small_class_symbols):
        """Small class (< 120 lines) should produce one chunk for the entire class."""
        chunks = chunker.chunk_file("service.py", small_class_code, small_class_symbols)
        symbol_chunks = [c for c in chunks if c.is_symbol_chunk]
        assert len(symbol_chunks) == 1
        assert "UserService" in symbol_chunks[0].content
        assert all(sid in symbol_chunks[0].symbol_ids for sid in [
            small_class_symbols[0].symbol_id,
            small_class_symbols[1].symbol_id,
        ])

    def test_standalone_function_chunk(self, chunker):
        code = "def hello():\n    return 'hi'\n\ndef world():\n    return 'world'\n"
        symbols = [
            Symbol(name="hello", kind=SymbolKind.FUNCTION, file_path="f.py",
                   start_line=1, end_line=2, signature="def hello()", language="python"),
            Symbol(name="world", kind=SymbolKind.FUNCTION, file_path="f.py",
                   start_line=4, end_line=5, signature="def world()", language="python"),
        ]
        chunks = chunker.chunk_file("f.py", code, symbols)
        func_chunks = [c for c in chunks if c.is_symbol_chunk]
        assert len(func_chunks) == 2

    def test_large_class_per_method_chunks(self, chunker):
        """Large class > 120 lines should be split per method."""
        config = ChunkingConfig(large_class_threshold=10)
        chunker = CodeChunker(config)
        # Create a class spanning 20 lines with 2 methods
        lines = ["class Big:\n"]
        lines.extend(["    pass\n"] * 5)
        lines.append("    def method_a(self):\n")
        lines.extend(["        pass\n"] * 5)
        lines.append("    def method_b(self):\n")
        lines.extend(["        pass\n"] * 5)
        code = "".join(lines)

        symbols = [
            Symbol(name="Big", kind=SymbolKind.CLASS, file_path="big.py",
                   start_line=1, end_line=len(lines), signature="class Big", language="python"),
            Symbol(name="method_a", kind=SymbolKind.METHOD, file_path="big.py",
                   start_line=7, end_line=12, signature="def method_a(self)", language="python",
                   container_name="Big"),
            Symbol(name="method_b", kind=SymbolKind.METHOD, file_path="big.py",
                   start_line=13, end_line=18, signature="def method_b(self)", language="python",
                   container_name="Big"),
        ]
        chunks = chunker.chunk_file("big.py", code, symbols)
        method_chunks = [c for c in chunks if c.is_symbol_chunk]
        assert len(method_chunks) == 2  # Per-method, not one big class chunk

    def test_uncovered_lines_get_chunked(self, chunker):
        """Lines not in any symbol should be chunked with sliding window."""
        code = "# Module docstring\nimport os\nimport sys\n\ndef func():\n    pass\n"
        symbols = [
            Symbol(name="func", kind=SymbolKind.FUNCTION, file_path="f.py",
                   start_line=5, end_line=6, signature="def func()", language="python"),
        ]
        chunks = chunker.chunk_file("f.py", code, symbols)
        non_symbol = [c for c in chunks if not c.is_symbol_chunk]
        assert len(non_symbol) >= 1  # The import section

    def test_empty_file_no_chunks(self, chunker):
        chunks = chunker.chunk_file("empty.py", "", [])
        assert len(chunks) == 0

    def test_no_symbols_sliding_window(self, chunker):
        code = "\n".join(f"# line {i}" for i in range(100))
        chunks = chunker.chunk_file("nocode.py", code, [])
        assert len(chunks) > 0
        assert all(not c.is_symbol_chunk for c in chunks)

    def test_embedding_text_has_header(self, chunker):
        code = "def hello():\n    pass\n"
        symbols = [
            Symbol(name="hello", kind=SymbolKind.FUNCTION, file_path="f.py",
                   start_line=1, end_line=2, signature="def hello()", language="python"),
        ]
        chunks = chunker.chunk_file("f.py", code, symbols)
        symbol_chunk = [c for c in chunks if c.is_symbol_chunk][0]
        assert "File: f.py" in symbol_chunk.embedding_text
        assert "Signature: def hello()" in symbol_chunk.embedding_text

    def test_chunks_sorted_by_start_line(self, chunker):
        code = "import os\n\ndef a():\n    pass\n\ndef b():\n    pass\n"
        symbols = [
            Symbol(name="b", kind=SymbolKind.FUNCTION, file_path="f.py",
                   start_line=6, end_line=7, signature="def b()", language="python"),
            Symbol(name="a", kind=SymbolKind.FUNCTION, file_path="f.py",
                   start_line=3, end_line=4, signature="def a()", language="python"),
        ]
        chunks = chunker.chunk_file("f.py", code, symbols)
        for i in range(len(chunks) - 1):
            assert chunks[i].start_line <= chunks[i + 1].start_line
