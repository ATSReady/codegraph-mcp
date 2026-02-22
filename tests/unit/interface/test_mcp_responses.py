from codegraph.interface.mcp.responses import McpMeta, ToolResponse, ErrorResponse


class TestMcpMeta:
    def test_meta_includes_schema_version(self):
        meta = McpMeta(server_version="0.3.0", request_id="7f2a", generation=8, stale=False, duration_ms=120)
        d = meta.to_dict()
        assert d["schema_version"] == 1
        assert "server_version" in d
        assert d["request_id"] == "7f2a"

    def test_tool_response_wraps_data_with_meta(self):
        meta = McpMeta(server_version="0.3.0", request_id="a1b2", generation=5, stale=True, duration_ms=50)
        resp = ToolResponse(meta=meta, data={"results": [1, 2, 3]})
        d = resp.to_dict()
        assert "_meta" in d
        assert d["_meta"]["stale"] is True
        assert d["results"] == [1, 2, 3]

    def test_error_response_format(self):
        resp = ErrorResponse(error="no_index", message="Run codegraph index")
        d = resp.to_dict()
        assert d["error"] == "no_index"
        assert d["message"] == "Run codegraph index"
