from codegraph.domain.errors import (
    CodegraphError, NoIndexError, ProviderUnavailableError,
    IndexLockedError, InvalidArgsError, ProviderMismatchError,
)


class TestErrors:
    def test_no_index_error_code(self):
        e = NoIndexError()
        assert e.error_code == "no_index"
        assert "codegraph index" in str(e)

    def test_provider_unavailable_error(self):
        e = ProviderUnavailableError("nomic-embed-text-v1.5")
        assert e.error_code == "provider_unavailable"

    def test_index_locked_error(self):
        e = IndexLockedError(pid=12345, hostname="devbox")
        assert e.error_code == "index_locked"

    def test_errors_serialize_to_dict(self):
        e = NoIndexError()
        d = e.to_dict()
        assert d["error"] == "no_index"
        assert "message" in d
