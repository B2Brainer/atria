"""Increment 6 — structured, size-rotated local logging."""

import json
import logging

from api.logging_config import LOG_BACKUP_COUNT, LOG_MAX_BYTES, configure_logging


def _reset_root_logger():
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)


def test_log_records_are_written_as_json_lines_to_the_configured_file(tmp_path):
    log_path = tmp_path / "backend.log"
    configure_logging(log_path)
    try:
        logging.getLogger("api.test").info("hello %s", "world")
        for handler in logging.getLogger().handlers:
            handler.flush()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["message"] == "hello world"
        assert record["level"] == "INFO"
    finally:
        _reset_root_logger()


def test_uncaught_exception_is_captured_as_a_log_record(tmp_path):
    log_path = tmp_path / "backend.log"
    configure_logging(log_path)
    try:
        logger = logging.getLogger("api.test")
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("backend process terminating due to an uncaught exception")
        for handler in logging.getLogger().handlers:
            handler.flush()

        lines = log_path.read_text().strip().splitlines()
        record = json.loads(lines[-1])
        assert "boom" in record["exception"]
    finally:
        _reset_root_logger()


def test_log_file_rotates_at_the_configured_size_and_retains_at_most_three_backups(tmp_path):
    log_path = tmp_path / "backend.log"
    configure_logging(log_path)
    try:
        logger = logging.getLogger("api.test")
        # Each record is small; write enough of them to force several
        # rotations well past the 5 MB threshold.
        chunk = "x" * 2000
        for _ in range(12000):
            logger.info(chunk)
        for handler in logging.getLogger().handlers:
            handler.flush()

        rotated = sorted(log_path.parent.glob(f"{log_path.name}.*"))
        assert len(rotated) == LOG_BACKUP_COUNT
        assert log_path.exists()
        assert log_path.stat().st_size <= LOG_MAX_BYTES + 4096
    finally:
        _reset_root_logger()
