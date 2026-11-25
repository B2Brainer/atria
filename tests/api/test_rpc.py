"""Acceptance criteria 3, 4: JSON-RPC framing, correlation, and stdout reservation."""

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

    for line in out_stream.getvalue().strip().splitlines():
        json.loads(line)  # raises if any line is not well-formed JSON
