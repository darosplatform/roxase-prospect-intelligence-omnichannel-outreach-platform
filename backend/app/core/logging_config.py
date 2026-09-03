"""Structured logging configuration.

* Local dev: human-readable text logs with timestamp/level/logger.
* Production: switch to JSON lines via the `LOG_JSON=true` env flag (no external
  dependency — a minimal json formatter is used). Each record also picks up the
  current request-id from a contextvar, if one is active, so logs are
  correlatable in tracing backends.
"""

from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """Format a LogRecord as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = current_request_id()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable single-line formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = current_request_id()
        if request_id:
            return f"{base} req_id={request_id}"
        return base


def configure_logging(log_json: bool | None = None) -> None:
    """Install the root handler/format. `log_json` overrides the env flag."""
    if log_json is None:
        log_json = os.environ.get("LOG_JSON", "false").lower() in ("1", "true", "yes")
    level = os.environ.get("APP_LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    if log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter("%(asctime)s %(levelname)s %(name)s  %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)