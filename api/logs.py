"""Structured JSON logs: one line per event, each carrying the request ID (spec, Logging).

Never log secrets or what a user typed in chat: log tool inputs, counts, tokens and outcomes.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from typing import Any

LOGGER_NAME = "tennis"
logger = logging.getLogger(LOGGER_NAME)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        return json.dumps(line, default=str)


def configure() -> None:
    """Send this app's events to stdout as JSON lines. Safe to call more than once."""
    if not any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def log_event(event: str, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, event, extra={"fields": fields})
