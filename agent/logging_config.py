"""Logging configuration.

By default emits human-readable logs. Set LOG_FORMAT=json for structured
output suitable for Azure App Service log aggregation.
"""

from __future__ import annotations

import json
import logging
import os
import sys


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Include any structured fields passed via `extra=`
        reserved = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
            "message",
            "asctime",
        }
        for k, v in record.__dict__.items():
            if k not in reserved and not k.startswith("_"):
                try:
                    json.dumps(v)
                    payload[k] = v
                except (TypeError, ValueError):
                    payload[k] = str(v)
        return json.dumps(payload, default=str)


_configured = False


def configure_logging() -> None:
    """Idempotent logging setup. Reads LOG_LEVEL and LOG_FORMAT from env."""
    global _configured
    if _configured:
        return

    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    fmt = os.environ.get("LOG_FORMAT", "text").lower()

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(level)
    # Replace any default handlers (e.g. Flask's) so format is consistent
    root.handlers = [handler]
    _configured = True
