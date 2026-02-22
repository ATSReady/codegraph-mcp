from codegraph.infrastructure.parsers.languages import (
    detect_language, get_grammar, LANGUAGE_EXTENSIONS, available_languages, get_parser,
)


class TestLanguageDetection:
    def test_python_detection(self):
        assert detect_language("src/auth/middleware.py") == "python"

    def test_typescript_detection(self):
        assert detect_language("src/routes/api.ts") == "typescript"

    def test_tsx_detection(self):
        assert detect_language("components/App.tsx") == "tsx"

    def test_javascript_detection(self):
        assert detect_language("index.js") == "javascript"

    def test_unknown_extension(self):
        assert detect_language("image.png") is None

    def test_available_languages_non_empty(self):
        langs = available_languages()
        assert len(langs) > 0
        assert any(l["name"] == "python" for l in langs)

    def test_get_parser_returns_parser(self):
        parser = get_parser("python")
        assert parser is not None

    def test_get_grammar_returns_language(self):
        grammar = get_grammar("python")
        assert grammar is not None
