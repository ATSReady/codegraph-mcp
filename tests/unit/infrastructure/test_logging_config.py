import json
import logging
import os
import pytest
from codegraph.infrastructure.logging_config import (
    setup_logging, get_request_logger, StructuredFormatter,
)


class TestStructuredFormatter:
    def test_format_basic(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="codegraph", level=logging.INFO, pathname="", lineno=0,
            msg="test message", args=(), exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "info"
        assert data["message"] == "test message"
        assert "timestamp" in data

    def test_format_with_extras(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="codegraph", level=logging.INFO, pathname="", lineno=0,
            msg="tool call", args=(), exc_info=None,
        )
        record.request_id = "abc123"
        record.duration_ms = 42
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "abc123"
        assert data["duration_ms"] == 42


class TestSetupLogging:
    def test_setup_console(self):
        logger = setup_logging(log_level="debug")
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1

    def test_setup_file(self, tmp_path):
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(log_file=log_file, log_level="info")
        logger.info("test")
        assert os.path.exists(log_file)

    def test_setup_non_structured(self):
        logger = setup_logging(structured=False)
        assert len(logger.handlers) == 1


class TestRequestLogger:
    def test_get_request_logger(self):
        adapter = get_request_logger("req-123")
        assert adapter.extra["request_id"] == "req-123"

    def test_auto_request_id(self):
        adapter = get_request_logger()
        assert len(adapter.extra["request_id"]) == 8
