"""
Shared structured logging for ewsmon.

Logs are emitted as single-line JSON for easy parsing and forwarding.
Use get_logger(__name__) in each module.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Default level from env (LOG_LEVEL=DEBUG). Also defined in app.settings for reference.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


class StructuredFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def __init__(self) -> None:
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Merge any extra fields (avoid overwriting standard keys)
        for k, v in record.__dict__.items():
            if k not in (
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "message", "taskName",
            ) and v is not None:
                payload[k] = v
        return json.dumps(payload, default=str)


def configure_root_logging(
    level: str | None = None,
    stream: Any = None,
) -> None:
    """
    Configure the root logger with structured JSON output.
    Call once at application startup (e.g. in main.py and worker.py).
    """
    lvl = (level or LOG_LEVEL).upper()
    numeric = getattr(logging, lvl, logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric)
    if not root.handlers:
        handler = logging.StreamHandler(stream or sys.stdout)
        handler.setFormatter(StructuredFormatter())
        root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger for the given module name.
    Prefer passing __name__ from the calling module.
    """
    return logging.getLogger(name)
