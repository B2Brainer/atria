"""Acceptance criterion 8: no log record produced by a representative run
that includes a credential operation (`set_credential`, `get_credential_status`,
`remove_credential`) contains the secret value, a resolved provider
authentication header, or sensitive interaction content -- checked against the
structured JSON-lines log FILE sink specifically (Increment 6), not merely
stderr (already covered by `tests/api/test_main_stdout_purity.py`).

Spawns the real `python -m api` entry point as a subprocess, exercises the
three credential operations (including one that fails, to exercise the
redacted-error log path in `api/rpc.py`), then reads back the structured log
file the subprocess wrote and asserts the secret never appears there, while
also positively confirming the credential-handling code path actually ran and
logged something.
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

# Deliberately NOT shaped like a real provider API key prefix (e.g. "sk-"):
# a literal secret-shaped string here would (correctly) trip Marshal's
# secrets scanner on this very test file. A random, unambiguously synthetic
# value is just as effective for the negative assertion below (it must never
# appear in the log file) without looking like real credential material.
_SECRET_VALUE = f"test-only-credential-{uuid.uuid4().hex}"


def test_log_file_never_contains_a_credential_secret_across_credential_operations(tmp_path):
    env = dict(os.environ)
    env["ATRIA_DB_PATH"] = str(tmp_path / "atria.sqlite3")
    env["ATRIA_KEYCHAIN_SERVICE"] = f"com.atria.credentials.test.{uuid.uuid4().hex[:8]}"
    log_path = tmp_path / "backend.log"
    env["ATRIA_LOG_PATH"] = str(log_path)

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

        messages = [
            {
                "id": 1,
                "method": "set_credential",
                "params": {"provider_id": "openai", "secret": _SECRET_VALUE},
            },
            {"id": 2, "method": "get_credential_status", "params": {"provider_id": "openai"}},
            {"id": 3, "method": "remove_credential", "params": {"provider_id": "openai"}},
            # Induce a genuine failure in a credential operation: an
            # unregistered provider_id raises (removal of an already-absent
            # credential is idempotent and does not fail), exercising
            # `api/rpc.py`'s redacted-error logging path for a credential
            # method.
            {"id": 4, "method": "remove_credential", "params": {"provider_id": "no-such-provider"}},
        ]
        for message in messages:
            process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

        responses = [json.loads(process.stdout.readline()) for _ in messages]
    finally:
        process.stdin.close()
        process.terminate()
        process.wait(timeout=5)

    assert responses[0]["id"] == 1
    assert "result" in responses[0]

    assert log_path.exists(), "the structured log file sink must have been created"
    log_text = log_path.read_text()

    # Negative assertion: the secret value must never appear in the log file,
    # in any record, in any form.
    assert _SECRET_VALUE not in log_text

    # Positive assertion: the credential-handling code path actually ran and
    # produced at least one log record referencing the operation (by method
    # name/provider id -- non-sensitive metadata), so the negative assertion
    # above isn't vacuously true over an empty or irrelevant log.
    log_lines = [json.loads(line) for line in log_text.strip().splitlines() if line.strip()]
    assert any(
        "credential" in record["message"] or "openai" in record["message"]
        for record in log_lines
    ), "expected at least one log record referencing the credential operation"
