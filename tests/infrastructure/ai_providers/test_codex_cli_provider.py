import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from atria.domain import AIRequest, AIResult, Purpose
from atria.infrastructure.ai_providers import codex_cli
from atria.infrastructure.ai_providers.codex_cli import (
    AIConfigurationError,
    CodexCLIProvider,
)
from atria.systems.ai import AIProvider, AIProviderError, AITimeoutError

REAL_WHICH = shutil.which
FAKE_BIN = "/fake/bin/codex"
LEAK = "token SECRET en /Users/alguien"
REQUEST = AIRequest(
    purpose=Purpose(text="Entender el ciclo de Atria"), instruction="Explica el ciclo"
)
ENV_VARS = ("ATRIA_CODEX_BIN", "ATRIA_AI_MODEL", "ATRIA_AI_TIMEOUT")


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """Entorno controlado: ni variables ni binario reales de la máquina."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(codex_cli.shutil, "which", lambda name: FAKE_BIN)
    monkeypatch.setattr(codex_cli.os, "getpgid", lambda pid: pid)
    return monkeypatch


class FakePopen:
    """Sustituye `subprocess.Popen`: registra la construcción y simula `.communicate()`."""

    def __init__(
        self,
        *,
        output: str | None = "respuesta",
        returncode: int = 0,
        construct_error: Exception | None = None,
        communicate_error: Exception | None = None,
    ):
        self.output = output
        self.returncode_value = returncode
        self.construct_error = construct_error
        self.communicate_error = communicate_error
        self.calls: list[tuple[list, dict]] = []
        self.communicate_calls: list[tuple[tuple, dict]] = []
        self.pid = 4242
        self.returncode: int | None = None

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.construct_error is not None:
            raise self.construct_error
        return self

    def communicate(self, *args, **kwargs):
        self.communicate_calls.append((args, kwargs))
        first_call = len(self.communicate_calls) == 1
        if first_call and self.communicate_error is not None:
            raise self.communicate_error
        if first_call and self.output is not None:
            Path(self.output_path).write_text(self.output, encoding="utf-8")
        self.returncode = self.returncode_value
        return (None, None)

    @property
    def args(self) -> list[str]:
        return self.calls[0][0]

    @property
    def kwargs(self) -> dict:
        return self.calls[0][1]

    @property
    def output_path(self) -> str:
        args = self.calls[-1][0]
        return args[args.index("--output-last-message") + 1]


def run_with(monkeypatch, fake: FakePopen) -> FakePopen:
    monkeypatch.setattr(codex_cli.subprocess, "Popen", fake)
    return fake


def test_implements_provider_port():
    assert isinstance(CodexCLIProvider(), AIProvider)


def test_invokes_codex_exec_safely_with_prompt_on_stdin(env):
    fake = run_with(env, FakePopen())

    CodexCLIProvider().complete(REQUEST)

    args, kwargs = fake.args, fake.kwargs
    assert isinstance(args, list) and args[:2] == [FAKE_BIN, "exec"]
    assert args[args.index("--sandbox") + 1] == "read-only"
    for flag in (
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-last-message",
        "--cd",
    ):
        assert flag in args
    assert args[-1] == "-"
    assert not kwargs.get("shell")
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] == subprocess.PIPE
    assert not any("Explica" in arg for arg in args)
    workdir = args[args.index("--cd") + 1]
    assert kwargs["cwd"] == Path(workdir)
    _comm_args, comm_kwargs = fake.communicate_calls[0]
    assert comm_kwargs["input"] == (
        "Propósito: Entender el ciclo de Atria\n\nExplica el ciclo"
    )
    assert comm_kwargs["timeout"] == codex_cli.DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize("model", [None, "", "gpt-test"])
def test_model_flag_only_when_configured(env, model):
    if model is not None:
        env.setenv("ATRIA_AI_MODEL", model)
    fake = run_with(env, FakePopen())

    CodexCLIProvider().complete(REQUEST)

    if model:
        assert fake.args[fake.args.index("--model") + 1] == model
    else:
        assert "--model" not in fake.args and "-m" not in fake.args


def test_no_dangerous_flags(env):
    env.setenv("ATRIA_AI_MODEL", "gpt-test")
    fake = run_with(env, FakePopen())

    CodexCLIProvider().complete(REQUEST)

    for arg in fake.args:
        for word in (
            "dangerously",
            "bypass",
            "approve-for-me",
            "--oss",
            "local-provider",
        ):
            assert word not in arg


def test_env_is_allowlisted_not_denylisted(env):
    """ATR-013 CPD (atr-013-provider-swap-v3): un deny-list de solo ATRIA_* deja pasar
    cualquier otro secreto del host a un agente con capacidad de shell. La lista debe
    ser de inclusión: solo lo que codex necesita para funcionar."""
    env.setenv("ATRIA_DATABASE_URL", "postgresql+psycopg://u:SECRET@h/db")
    env.setenv("PATH", "/usr/bin")
    env.setenv("HOME", "/home/atria")
    env.setenv("LANG", "es_ES.UTF-8")
    env.setenv("LC_ALL", "es_ES.UTF-8")
    env.setenv("CODEX_HOME", "/home/atria/.codex")
    env.setenv("GITHUB_TOKEN", "ghp_SECRET")
    env.setenv("AWS_SECRET_ACCESS_KEY", "AWS_SECRET")
    env.setenv("NPM_TOKEN", "npm_SECRET")
    fake = run_with(env, FakePopen())

    CodexCLIProvider().complete(REQUEST)

    passed = fake.kwargs["env"]
    assert passed["PATH"] == "/usr/bin"
    assert passed["HOME"] == "/home/atria"
    assert passed["LANG"] == "es_ES.UTF-8"
    assert passed["LC_ALL"] == "es_ES.UTF-8"
    assert passed["CODEX_HOME"] == "/home/atria/.codex"
    for leaked in (
        "ATRIA_DATABASE_URL",
        "GITHUB_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "NPM_TOKEN",
    ):
        assert leaked not in passed


def test_output_becomes_result_and_tempdir_is_removed(env):
    fake = run_with(env, FakePopen(output="respuesta final\n"))

    result = CodexCLIProvider().complete(REQUEST)

    assert result == AIResult(content="respuesta final")
    assert not Path(fake.output_path).parent.exists()


def test_timeout_becomes_ai_timeout_error(env):
    fake = run_with(
        env, FakePopen(communicate_error=subprocess.TimeoutExpired("codex", 30))
    )
    killpg_calls = []
    env.setattr(
        codex_cli.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig))
    )

    with pytest.raises(AITimeoutError) as raised:
        CodexCLIProvider().complete(REQUEST)

    assert raised.value.__cause__ is None and raised.value.__suppress_context__
    assert not Path(fake.output_path).parent.exists()


def test_timeout_kills_the_whole_process_group(env):
    """ATR-013 CPD (atr-013-provider-swap-v3): `subprocess.run` solo mata al hijo
    directo; un nieto que `codex exec` genere sobrevive. El grupo completo debe morir."""
    fake = run_with(
        env, FakePopen(communicate_error=subprocess.TimeoutExpired("codex", 30))
    )
    killpg_calls = []
    env.setattr(
        codex_cli.os, "killpg", lambda pgid, sig: killpg_calls.append((pgid, sig))
    )

    with pytest.raises(AITimeoutError):
        CodexCLIProvider().complete(REQUEST)

    assert killpg_calls == [(fake.pid, codex_cli.signal.SIGKILL)]
    # tras matar al grupo, se reaprovecha (reap) el proceso: segunda llamada a communicate()
    assert len(fake.communicate_calls) == 2


def test_timeout_kill_tolerates_process_already_gone(env):
    run_with(env, FakePopen(communicate_error=subprocess.TimeoutExpired("codex", 30)))

    def _raise_gone(pgid, sig):
        raise ProcessLookupError

    env.setattr(codex_cli.os, "killpg", _raise_gone)

    with pytest.raises(AITimeoutError):
        CodexCLIProvider().complete(REQUEST)


@pytest.mark.parametrize(
    "fake",
    [
        pytest.param(FakePopen(returncode=1), id="salida-distinta-de-0"),
        pytest.param(FakePopen(output=""), id="archivo-vacio"),
        pytest.param(FakePopen(output="  \n"), id="archivo-en-blanco"),
        pytest.param(FakePopen(output=None), id="archivo-ausente"),
        pytest.param(
            FakePopen(construct_error=FileNotFoundError(2, LEAK)),
            id="binario-inexistente",
        ),
        pytest.param(
            FakePopen(construct_error=PermissionError(13, LEAK)), id="sin-permiso"
        ),
    ],
)
def test_failures_become_generic_provider_error(env, fake):
    run_with(env, fake)

    with pytest.raises(AIProviderError) as raised:
        CodexCLIProvider().complete(REQUEST)

    assert type(raised.value) is AIProviderError
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    "fake",
    [
        FakePopen(returncode=1),
        FakePopen(output=None),
        FakePopen(communicate_error=subprocess.TimeoutExpired("codex", 30)),
        FakePopen(construct_error=FileNotFoundError(2, LEAK)),
    ],
)
def test_process_output_never_leaks(env, caplog, fake):
    caplog.set_level(logging.DEBUG)
    run_with(env, fake)

    with pytest.raises((AIProviderError, AITimeoutError)) as raised:
        CodexCLIProvider().complete(REQUEST)

    for text in (str(raised.value), caplog.text):
        assert "SECRET" not in text and "/Users/" not in text
    error = raised.value
    # Sin la excepción original encadenada: ni causa ni contexto visibles en la traza.
    assert error.__cause__ is None
    assert error.__context__ is None or error.__suppress_context__


def test_missing_binary_raises_clear_configuration_error(env, tmp_path):
    env.setattr(codex_cli.shutil, "which", REAL_WHICH)
    env.setenv("ATRIA_CODEX_BIN", str(tmp_path / "no-existe" / "codex"))

    with pytest.raises(AIConfigurationError, match="codex"):
        CodexCLIProvider()


def test_binary_is_resolved_from_env(env):
    seen = []
    env.setattr(codex_cli.shutil, "which", lambda name: seen.append(name) or FAKE_BIN)
    env.setenv("ATRIA_CODEX_BIN", " /opt/codex ")

    CodexCLIProvider()

    assert seen == ["/opt/codex"]


@pytest.mark.parametrize("value", ["abc", "0", "-1", "nan", "inf"])
def test_invalid_timeout_raises_clear_error(env, value):
    env.setenv("ATRIA_AI_TIMEOUT", value)

    with pytest.raises(AIConfigurationError, match="ATRIA_AI_TIMEOUT"):
        CodexCLIProvider()


def test_valid_timeout_is_passed_to_process(env):
    env.setenv("ATRIA_AI_TIMEOUT", "2.5")
    fake = run_with(env, FakePopen())

    CodexCLIProvider().complete(REQUEST)

    _, comm_kwargs = fake.communicate_calls[0]
    assert comm_kwargs["timeout"] == 2.5


@pytest.mark.integration
@pytest.mark.skipif(REAL_WHICH("codex") is None, reason="requiere `codex` en el PATH")
def test_real_call(monkeypatch):
    # El fixture `env` sustituye entorno y binario; aquí se restauran los reales.
    monkeypatch.undo()
    monkeypatch.setenv("ATRIA_AI_TIMEOUT", "300")

    result = CodexCLIProvider().complete(
        AIRequest(
            purpose=Purpose(text="Probar la integración"),
            instruction="Responde solo con la palabra: listo",
        )
    )

    assert result.content.strip()
