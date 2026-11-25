"""Acceptance criterion 4: process stdout, across a representative run
including a log-producing code path, carries only well-formed JSON-RPC
messages — diagnostic output goes to stderr only.

Spawns the real `python -m api` entry point as a subprocess (not a stubbed
stream), sends one failing request (unknown method, which `RpcDispatcher`
logs via `logger.warning`) alongside one successful one, and inspects the
subprocess's actual stdout/stderr file descriptors directly.
"""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

if sys.platform != "darwin":
    pytest.skip(
        "api/'s composition wires a real CredentialAdapter (darwin only); see "
        "tests/api/conftest.py.",
        allow_module_level=True,
    )

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_stdout_carries_only_json_rpc_messages_even_when_a_request_fails(tmp_path):
    env = dict(os.environ)
    env["ATRIA_DB_PATH"] = str(tmp_path / "atria.sqlite3")
    env["ATRIA_KEYCHAIN_SERVICE"] = f"com.atria.credentials.test.{uuid.uuid4().hex[:8]}"

    process = subprocess.Popen(
        [sys.executable, "-m", "api"],
        cwd=REPO_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        ready_line = process.stdout.readline()
        assert json.loads(ready_line)["event"] == "ready"

        missing_record_id = str(uuid.uuid4())
        get_message = {"id": 1, "method": "get", "params": {"record_id": missing_record_id}}
        process.stdin.write(json.dumps(get_message) + "\n")
        process.stdin.write(json.dumps({"id": 2, "method": "list_cycles", "params": {}}) + "\n")
        process.stdin.flush()

        error_response = json.loads(process.stdout.readline())
        ok_response = json.loads(process.stdout.readline())
    finally:
        process.stdin.close()
        process.terminate()
        stderr_output = process.stderr.read()
        process.wait(timeout=5)

    assert error_response["id"] == 1
    assert "error" in error_response and "result" not in error_response
    assert ok_response == {"id": 2, "result": []}
    # The handler's failure is logged (via api.rpc's logger.warning), and it
    # must have landed on stderr, not been silently dropped or sent to stdout.
    assert "method %r failed" not in stderr_output  # the format string itself, unsubstituted
    assert "get" in stderr_output
