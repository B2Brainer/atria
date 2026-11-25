"""Entry point for the Python backend subprocess: `python -m api`.

Electron's main process spawns this as a child process and communicates
with it over its stdin/stdout (per Increment 5's resolved IPC transport).
Logging is configured to stderr and to a local, structured, size-rotated
log file (Increment 6) — stdout remains reserved for JSON-RPC protocol
messages only.
"""

from __future__ import annotations

import logging
import sys

from api import config
from api.composition import Composition
from api.handlers import Handlers, dispatch_table
from api.logging_config import configure_logging
from api.rpc import RpcDispatcher, serve

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging(config.log_path())

    try:
        composition = Composition()
        handlers = Handlers(composition)
        dispatcher = RpcDispatcher(dispatch_table(handlers))
        serve(dispatcher, sys.stdin, sys.stdout)
    except Exception:
        # Crash diagnostic (Increment 6): an uncaught exception reaching this
        # point would otherwise exit the process with only Python's default
        # traceback-to-stderr behavior — captured here as a log record (to
        # both the stderr and structured file sinks) before re-raising, so
        # the real exit code/traceback are unchanged for the caller.
        logger.exception("backend process terminating due to an uncaught exception")
        raise


if __name__ == "__main__":
    main()
