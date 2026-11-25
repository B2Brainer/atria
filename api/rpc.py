"""Line-delimited JSON-RPC dispatch over a backend subprocess's stdin/stdout.

Per Increment 5 Expected Behavior item 2: each request carries an `id`; each
response carries the same `id`. A successful response carries `result`; a
failed response carries `error` instead — never both, never neither. Protocol
stdout carries only these messages: this module is the sole writer to the
given output stream, and the only way a caller may produce stdout output is
through its handler's return value / raised exception — nothing here ever
calls `print()` or lets a handler's own logging reach this stream. All
diagnostic logging goes through the standard `logging` module, configured
(by `api/__main__.py`) to write to stderr, never to this module's output
stream.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import IO, Any

logger = logging.getLogger(__name__)

# Credential operations resolve or compare against a secret internally
# (api/handlers.py). A raw str(exc) from these three alone is never safe to
# put on the wire or into a log: an adapter failure mode this dispatcher
# cannot enumerate in advance (a future CredentialPort implementation, an
# unexpected keychain error variant) could embed secret-shaped text in its
# message. Every other operation's exceptions carry no secret material by
# construction (core/ exceptions reference ids/references, never a resolved
# value) and keep their original, more diagnosable text.
_CREDENTIAL_METHODS = frozenset(
    {"set_credential", "get_credential_status", "remove_credential"}
)
_REDACTED_CREDENTIAL_ERROR = "credential operation failed"


class RpcDispatcher:
    def __init__(self, methods: dict[str, Callable[..., Any]]) -> None:
        self._methods = methods

    def dispatch(self, message: dict) -> dict | None:
        if not isinstance(message, dict):
            # Never log the message's own content: a non-object line could
            # itself be a bare secret-shaped string (e.g. a client mistake
            # sending a raw value instead of a JSON-RPC envelope), and this
            # path has no way to know. Only its type is safe to report.
            logger.warning(
                "malformed JSON-RPC message: expected an object, got %s", type(message).__name__
            )
            return _error(None, "malformed JSON-RPC message: expected an object")

        request_id = message.get("id")
        method_name = message.get("method")
        params = message.get("params") or {}

        method = self._methods.get(method_name)
        if method is None:
            return _error(request_id, f"unknown method: {method_name!r}")

        try:
            result = method(**params) if isinstance(params, dict) else method(*params)
        except Exception as exc:  # noqa: BLE001 - any core/adapter failure propagates as an RPC error
            if method_name in _CREDENTIAL_METHODS:
                logger.warning("method %r failed: %s", method_name, _REDACTED_CREDENTIAL_ERROR)
                return _error(request_id, _REDACTED_CREDENTIAL_ERROR)
            logger.warning("method %r failed: %s", method_name, exc)
            return _error(request_id, str(exc))
        return {"id": request_id, "result": result}


def _error(request_id: Any, message: str) -> dict:
    return {"id": request_id, "error": {"message": message}}


def write_ready(out: IO[str]) -> None:
    out.write(json.dumps({"id": None, "event": "ready"}) + "\n")
    out.flush()


def serve(dispatcher: RpcDispatcher, in_stream: IO[str], out_stream: IO[str]) -> None:
    write_ready(out_stream)
    for line in in_stream:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("malformed JSON-RPC line: %s", exc)
            response = _error(None, "malformed JSON-RPC message")
        else:
            response = dispatcher.dispatch(message)
        if response is not None:
            out_stream.write(json.dumps(response) + "\n")
            out_stream.flush()
