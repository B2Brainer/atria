"""Structured (JSON-lines), size-rotated local logging for the Python backend.

Per Increment 6's resolved logging requirement: in addition to the stderr
framing already established for diagnostics in Increment 5 (unchanged —
stdout remains exclusively protocol messages), every log record is also
written as a single JSON line to a local, size-rotated log file: a maximum
individual file size of 5 MB, with at most 3 rotated files retained (4 files
total on disk, including the active one).

No log record may ever contain a resolved secret, a credential reference's
secret value, a raw provider authentication header, or sensitive interaction
content (a raw prompt/response body) — `api/rpc.py` already redacts
credential-operation failures before they reach the logger, and no other
`core`/`adapter` exception in this codebase embeds request/response content
(verified: exception messages reference only ids/references). This module
performs no redaction itself; it is a structured sink for records that are
already safe to persist.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import time
from pathlib import Path

LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


class JsonLinesFormatter(logging.Formatter):
    """Renders a log record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(record.created)
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(log_path: Path | str) -> None:
    """Configures the root logger with both an stderr sink (Increment 5's
    established plain-text diagnostics, unchanged) and a structured,
    size-rotated JSON-lines file sink (this increment's addition)."""

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(stderr_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(JsonLinesFormatter())
    root.addHandler(file_handler)
