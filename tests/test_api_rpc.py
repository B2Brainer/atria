"""Acceptance criteria 3, 4: JSON-RPC framing, correlation, and stdout reservation.

Lives outside tests/api/ deliberately: RpcDispatcher itself has no
platform dependency, and (since api/handlers.py's Composition import is
now TYPE_CHECKING-only) neither does importing api.handlers for
OPERATIONS/_CREDENTIAL_METHODS — this file's tests must run on every CI
runner, not just macOS (tests/api/conftest.py skips its whole directory
on non-darwin because api/composition.py wires a real CredentialAdapter)."""

import io
import json

from api.rpc import RpcDispatcher, serve


def test_response_carries_the_same_id_as_the_request():
    dispatcher = RpcDispatcher({"echo": lambda value: value})
    message = {"id": 42, "method": "echo", "params": {"value": "x"}}
    in_stream = io.StringIO(json.dumps(message) + "\n")
    out_stream = io.StringIO()

    serve(dispatcher, in_stream, out_stream)

    lines = out_stream.getvalue().strip().splitlines()
    ready, response = json.loads(lines[0]), json.loads(lines[1])
    assert ready["event"] == "ready"
    assert response["id"] == 42
    assert response["result"] == "x"
    assert "error" not in response


def test_failed_response_carries_error_not_result():
    def failing():
        raise ValueError("boom")

    dispatcher = RpcDispatcher({"fail": failing})
    in_stream = io.StringIO(json.dumps({"id": 7, "method": "fail", "params": {}}) + "\n")
    out_stream = io.StringIO()

    serve(dispatcher, in_stream, out_stream)

    lines = out_stream.getvalue().strip().splitlines()
    response = json.loads(lines[1])
    assert response["id"] == 7
    assert "error" in response
    assert "result" not in response


def test_unknown_method_produces_a_distinguishable_error():
    dispatcher = RpcDispatcher({})

    response = dispatcher.dispatch({"id": 1, "method": "nope", "params": {}})

    assert response["id"] == 1
    assert "error" in response


def test_a_valid_json_non_object_line_is_a_protocol_error_not_a_crash():
    # A line can be valid JSON yet not a JSON-RPC object (`null`, `[]`, `"x"`,
    # `42`) — dispatch() must reject it as a protocol error rather than raise
    # an uncaught AttributeError from `.get()` on a non-dict.
    dispatcher = RpcDispatcher({"echo": lambda value: value})

    for malformed in (None, [], "x", 42):
        response = dispatcher.dispatch(malformed)
        assert response is not None
        assert "error" in response and "result" not in response


def test_a_non_object_message_is_never_logged_verbatim(caplog):
    # A non-object line could itself be a bare secret-shaped string (a
    # client mistake sending a raw value instead of an envelope) — the log
    # line must report only the message's type, never its content.
    dispatcher = RpcDispatcher({})
    secret_shaped = "test-this-must-never-appear-in-a-log-line"

    # level=0 (NOTSET) captures every level, not just WARNING-and-above.
    with caplog.at_level(0):
        dispatcher.dispatch(secret_shaped)

    assert secret_shaped not in caplog.text
    assert len(caplog.records) == 1
    assert caplog.records[0].args == (type(secret_shaped).__name__,)


def test_credential_methods_are_exactly_the_three_credential_operations():
    from api.handlers import OPERATIONS
    from api.rpc import _CREDENTIAL_METHODS

    assert _CREDENTIAL_METHODS == {"set_credential", "get_credential_status", "remove_credential"}
    assert _CREDENTIAL_METHODS <= set(OPERATIONS)


def test_credential_operation_exceptions_are_redacted_not_passed_through(caplog):
    # Any failure from set_credential/get_credential_status/remove_credential
    # returns a fixed, generic message — never str(exc) — since a future
    # CredentialPort implementation's exception text is not something this
    # dispatcher can guarantee is secret-free. This must hold for the log
    # line too, not just the RPC response: rpc.py redacts both.
    secret_value = "test-should-never-appear"

    # The inner parameter must be named `secret` (not just here but) to
    # match the "secret" key in the params dict below -- dispatch() calls
    # method(**params), so a different parameter name would raise a
    # TypeError that this test's generic exception handling would then
    # mask entirely, never exercising the intended leaky-secret path.
    # calls records each invocation's actual arguments: a positive
    # assertion that the leaky handler itself ran with the right secret,
    # not just a TypeError from a keyword-binding break that this
    # dispatcher's generic exception handling would otherwise mask
    # identically (exactly the regression 132cb3b introduced).
    calls: list[tuple[str, str]] = []

    def leaky_set_credential(provider_id: str, secret: str) -> None:
        calls.append((provider_id, secret))
        raise RuntimeError(f"failed storing {secret!r} for {provider_id!r}")

    dispatcher = RpcDispatcher({"set_credential": leaky_set_credential})

    # level=0 (NOTSET) captures every level, not just WARNING-and-above.
    with caplog.at_level(0):
        response = dispatcher.dispatch(
            {
                "id": 1,
                "method": "set_credential",
                "params": {"provider_id": "openai", "secret": secret_value},
            }
        )

    assert calls == [("openai", secret_value)]
    assert secret_value not in json.dumps(response)
    assert response["error"]["message"] == "credential operation failed"
    assert len(caplog.records) == 1  # a record WAS emitted — not just secret-free if present
    assert secret_value not in caplog.text
    assert "failed storing" not in caplog.text  # the leaky exception's own message


def test_every_output_line_is_well_formed_json_only_protocol_messages():
    dispatcher = RpcDispatcher({"echo": lambda value: value})
    in_stream = io.StringIO(
        "\n".join(
            json.dumps({"id": i, "method": "echo", "params": {"value": i}}) for i in range(5)
        )
        + "\n"
    )
    out_stream = io.StringIO()

    serve(dispatcher, in_stream, out_stream)

    lines = out_stream.getvalue().split("\n")
    assert lines[-1] == ""  # every written line ends in \n; no partial trailing line
    for line in lines[:-1]:
        # A blank line would itself be a framing break (not well-formed
        # JSON) — it must fail here, not be silently tolerated.
        parsed = json.loads(line)
        assert isinstance(parsed, dict)  # a JSON-RPC message, not a bare scalar/array
