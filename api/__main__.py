"""Entry point for the Python backend subprocess: `python -m api`.

Electron's main process spawns this as a child process and communicates
with it over its stdin/stdout (per Increment 5's resolved IPC transport).
Logging is configured to stderr exclusively, so stdout is reserved for
JSON-RPC protocol messages only.
"""

from __future__ import annotations

import logging
import sys

from api.composition import Composition
from api.handlers import Handlers
from api.rpc import RpcDispatcher, serve


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    composition = Composition()
    handlers = Handlers(composition)
    dispatcher = RpcDispatcher(
        {
            "initiate": handlers.initiate,
            "get": handlers.get,
            "list_by_cycle": handlers.list_by_cycle,
            "list_cycles": handlers.list_cycles,
            "set_credential": handlers.set_credential,
            "get_credential_status": handlers.get_credential_status,
            "remove_credential": handlers.remove_credential,
        }
    )
    serve(dispatcher, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
