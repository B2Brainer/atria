import json
import logging
import os

import httpx2
import pytest

from atria.domain import AIRequest, AIResult, Purpose
from atria.infrastructure.ai_providers.openai import (
    AIConfigurationError,
    OpenAIProvider,
)
from atria.systems.ai import AIProvider, AIProviderError, AITimeoutError

KEY = "sk-test-SECRET"
RAW_TEXT = "RAW-PROVIDER-TEXT"
REQUEST = AIRequest(
    purpose=Purpose(text="Entender el ciclo de Atria"), instruction="Explica el ciclo"
)
ENV_VARS = ("OPENAI_API_KEY", "ATRIA_AI_MODEL", "ATRIA_AI_TIMEOUT")


@pytest.fixture(autouse=True)
def env(monkeypatch):
    """Entorno controlado: ninguna variable real de la máquina entra en los tests."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("ATRIA_AI_MODEL", "modelo-test")
    return monkeypatch


def completion(content: str | None) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "modelo-test",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
    }


def provider(handler) -> OpenAIProvider:
    """Provider con el SDK real y el transporte HTTP mockeado: sin red."""
    return OpenAIProvider(
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )


def respond(status: int, body: dict):
    return lambda request: httpx2.Response(status, json=body)


def fail(error_type):
    def handler(request):
        raise error_type(RAW_TEXT, request=request)

    return handler


def error_body(status: int) -> dict:
    return {"error": {"message": f"{RAW_TEXT} {KEY}", "type": "error", "code": status}}


def test_implements_provider_port():
    assert isinstance(provider(respond(200, completion("ok"))), AIProvider)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OPENAI_API_KEY", None),
        ("OPENAI_API_KEY", "   "),
        ("ATRIA_AI_MODEL", None),
        ("ATRIA_AI_TIMEOUT", "abc"),
        ("ATRIA_AI_TIMEOUT", "0"),
        ("ATRIA_AI_TIMEOUT", "-1"),
        ("ATRIA_AI_TIMEOUT", "nan"),
        ("ATRIA_AI_TIMEOUT", "inf"),
    ],
)
def test_missing_or_invalid_config_raises_clear_error_without_secret(env, name, value):
    if value is None:
        env.delenv(name)
    else:
        env.setenv(name, value)

    with pytest.raises(AIConfigurationError, match=name) as raised:
        OpenAIProvider()

    assert "SECRET" not in str(raised.value)


def test_valid_timeout_is_accepted(env):
    env.setenv("ATRIA_AI_TIMEOUT", "2.5")

    assert provider(respond(200, completion("ok"))).complete(REQUEST).content == "ok"


def test_valid_response_becomes_ai_result():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=completion("respuesta"))

    result = provider(handler).complete(REQUEST)

    assert result == AIResult(content="respuesta")
    assert sent[0]["model"] == "modelo-test"
    assert sent[0]["messages"] == [
        {"role": "system", "content": "Propósito: Entender el ciclo de Atria"},
        {"role": "user", "content": "Explica el ciclo"},
    ]


def test_response_without_content_raises_provider_error():
    with pytest.raises(AIProviderError, match="sin contenido"):
        provider(respond(200, completion(None))).complete(REQUEST)


def test_response_without_choices_raises_provider_error():
    body = completion("ok") | {"choices": []}

    with pytest.raises(AIProviderError, match="sin contenido"):
        provider(respond(200, body)).complete(REQUEST)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_become_generic_provider_error(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(status, json=error_body(status))

    with pytest.raises(AIProviderError) as raised:
        provider(handler).complete(REQUEST)

    error = raised.value
    assert type(error) is AIProviderError
    assert str(error) == f"el proveedor de IA respondió con estado {status}"
    assert error.__cause__ is None and error.__suppress_context__
    assert len(calls) == 1  # sin reintentos ocultos del SDK


@pytest.mark.parametrize(
    ("transport_error", "expected"),
    [
        (httpx2.ReadTimeout, AITimeoutError),
        (httpx2.ConnectTimeout, AITimeoutError),
        (httpx2.ConnectError, AIProviderError),
    ],
)
def test_transport_errors_are_mapped(transport_error, expected):
    with pytest.raises(AIProviderError) as raised:
        provider(fail(transport_error)).complete(REQUEST)

    assert type(raised.value) is expected
    assert RAW_TEXT not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_secret_never_appears_in_logs(caplog):
    caplog.set_level(logging.DEBUG)
    errors = []

    provider(respond(200, completion("ok"))).complete(REQUEST)
    for handler in (respond(401, error_body(401)), fail(httpx2.ReadTimeout)):
        with pytest.raises(AIProviderError) as raised:
            provider(handler).complete(REQUEST)
        errors.append(str(raised.value))

    assert caplog.records  # el SDK sí loguea a DEBUG: el test no es vacuo
    assert "SECRET" not in caplog.text
    assert not any("SECRET" in error for error in errors)


@pytest.mark.integration
@pytest.mark.skipif(
    not (os.environ.get("OPENAI_API_KEY") and os.environ.get("ATRIA_AI_MODEL")),
    reason="requiere OPENAI_API_KEY y ATRIA_AI_MODEL",
)
def test_real_call(monkeypatch):
    # El fixture `env` sustituye las variables; aquí se restauran las reales.
    monkeypatch.undo()

    result = OpenAIProvider().complete(REQUEST)

    assert result.content.strip()
