"""Structured logging with rotation."""
from __future__ import annotations

import json
import logging
import os
import uuid
from logging.handlers import RotatingFileHandler
from typing import Optional


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include extra fields if present
        for key in ("request_id", "duration_ms", "generation", "stale", "tool", "file_count"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
        
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)


def setup_logging(
    log_file: Optional[str] = None,
    log_level: str = "info",
    max_size_mb: int = 10,
    keep_rotations: int = 3,
    structured: bool = True,
) -> logging.Logger:
    """Configure logging for codegraph."""
    logger = logging.getLogger("codegraph")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Clear existing handlers
    logger.handlers.clear()

    if log_file:
        os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else ".", exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_size_mb * 1024 * 1024,
            backupCount=keep_rotations,
        )
    else:
        handler = logging.StreamHandler()

    if structured:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))

    logger.addHandler(handler)
    return logger


def get_request_logger(request_id: Optional[str] = None) -> logging.LoggerAdapter:
    """Get a logger adapter with request_id context."""
    if request_id is None:
        request_id = str(uuid.uuid4())[:8]
    logger = logging.getLogger("codegraph")
    return logging.LoggerAdapter(logger, {"request_id": request_id})
