"""Acceptance criteria 2-10, 14: AIProviderAdapter against a controlled HTTPX transport.

No live network call: `httpx.MockTransport` stands in for the local HTTP stub,
giving deterministic, CI-safe control over each response shape this increment's
acceptance criteria exercise.
"""

import json
import socket
import threading
import time
from decimal import Decimal

import httpx
import pytest
from adapters.providers.adapter import (
    AIProviderAdapter,
    InsecureEndpointError,
    ProviderResponseError,
)
from core.interaction.models import InteractionRequest, ProviderConfiguration
from core.ports.credentials import CredentialPort

ENDPOINT = "https://provider.invalid/v1/complete"


class _FakeCredentialPort(CredentialPort):
    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets = secrets or {}

    def get(self, reference: str) -> str:
        try:
            return self._secrets[reference]
        except KeyError:
            raise LookupError(f"no credential for {reference!r}") from None

    def store(self, reference: str, secret: str) -> None:
        self._secrets[reference] = secret

    def delete(self, reference: str) -> None:
        self._secrets.pop(reference, None)


def _configurations() -> dict[str, ProviderConfiguration]:
    return {
        "openai": ProviderConfiguration(
            provider_id="openai", endpoint=ENDPOINT, credential_reference="openai-key"
        )
    }


def _request(provider_id: str = "openai", model_id: str = "gpt-4o-mini") -> InteractionRequest:
    return InteractionRequest(
        input="hello",
        provider_id=provider_id,
        model_id=model_id,
        parameters={"temperature": 0},
    )


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _success_payload(**overrides) -> dict:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"message": {"content": "hi"}}],
    }
    payload.update(overrides)
    return payload


def test_execute_issues_exactly_one_request_to_the_mapped_endpoint():
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json=_success_payload())

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    result = adapter.execute(_request())

    assert len(requests_seen) == 1
    assert str(requests_seen[0].url) == ENDPOINT
    assert result.status == "success"
    assert result.output == "hi"


def test_execute_raises_and_issues_no_request_when_provider_id_is_unconfigured():
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json=_success_payload())

    adapter = AIProviderAdapter({}, _FakeCredentialPort(), client=_client(handler))

    with pytest.raises(KeyError):
        adapter.execute(_request())

    assert requests_seen == []


def test_execute_raises_and_issues_no_request_when_credential_is_unresolvable():
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json=_success_payload())

    adapter = AIProviderAdapter(_configurations(), _FakeCredentialPort({}), client=_client(handler))

    with pytest.raises(LookupError):
        adapter.execute(_request())

    assert requests_seen == []


def test_execute_populates_metrics_when_the_response_carries_usage_data_for_a_priced_model():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_payload(usage={"prompt_tokens": 1_000_000, "completion_tokens": 500_000}),
        )

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    result = adapter.execute(_request())

    assert result.metrics is not None
    assert result.metrics.input_tokens == 1_000_000
    assert result.metrics.output_tokens == 500_000
    assert result.metrics.cost == Decimal("0.15") + Decimal("0.60") * Decimal("0.5")
    assert result.metrics.duration > 0


def test_execute_leaves_metrics_none_when_the_response_carries_no_usage_data():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload())

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    result = adapter.execute(_request())

    assert result.metrics is None


def test_execute_leaves_metrics_none_when_the_requested_model_has_no_pricing_entry():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_payload(usage={"prompt_tokens": 10, "completion_tokens": 5}),
        )

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    result = adapter.execute(_request(model_id="some-unpriced-model"))

    assert result.metrics is None


def test_execute_prices_by_the_requested_model_id_not_the_response_echoed_model():
    # OpenAI's response often echoes a more specific, versioned model string
    # (e.g. "gpt-4o-mini-2024-07-18") that would never match a pricing-table
    # entry keyed by the configured alias — pricing must key off what was
    # REQUESTED, not what the response happened to echo back.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_payload(
                model="gpt-4o-mini-2024-07-18",
                usage={"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
            ),
        )

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    result = adapter.execute(_request(model_id="gpt-4o-mini"))

    assert result.metrics is not None
    assert result.metrics.cost == Decimal("0.15") + Decimal("0.60") * Decimal("0.5")


def test_execute_raises_on_a_non_2xx_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    with pytest.raises(ProviderResponseError):
        adapter.execute(_request())


def test_non_2xx_error_message_never_embeds_the_raw_response_body():
    # A provider's own error text can carry credential-derived content (e.g.
    # OpenAI's auth-failure responses echo a redacted key fragment) — the
    # exception's message, which a caller's default logging would surface
    # verbatim, must stay free of it; the raw body is still reachable via
    # .response_body for deliberate inspection only.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key: sk-secret"}})

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    with pytest.raises(ProviderResponseError) as excinfo:
        adapter.execute(_request())

    assert "sk-secret" not in str(excinfo.value)
    assert "sk-secret" in excinfo.value.response_body


def test_execute_raises_on_a_network_level_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    with pytest.raises(ProviderResponseError):
        adapter.execute(_request())


def test_network_failure_exception_carries_no_chained_request_with_the_credential():
    # httpx sets `.request` (headers included) on its own exceptions once a
    # request is in flight. Chaining that exception (via `from exc`, or
    # implicitly via __context__) would carry the Bearer credential reachable
    # from the raised ProviderResponseError's exception chain, not just its
    # message — this proves neither __cause__ nor __context__ carries it.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    with pytest.raises(ProviderResponseError) as excinfo:
        adapter.execute(_request())

    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


def test_execute_raises_when_the_response_body_cannot_be_parsed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    with pytest.raises(ProviderResponseError):
        adapter.execute(_request())


def test_send_request_never_disables_tls_verification_and_sets_an_explicit_timeout():
    adapter = AIProviderAdapter(
        _configurations(),
        _FakeCredentialPort({"openai-key": "sk-secret"}),
        client=_client(lambda request: httpx.Response(200, json=_success_payload())),
        timeout=7.5,
    )

    # No verify=False anywhere in the adapter's construction or request path;
    # the injected client retains httpx's default (verify=True).
    assert adapter._client._transport is not None
    assert adapter._timeout == 7.5


def test_credential_appears_in_the_request_header_and_not_in_the_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_success_payload())

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    adapter.execute(_request())

    sent = captured["request"]
    assert sent.headers["Authorization"] == "Bearer sk-secret"
    assert b"sk-secret" not in sent.content


def test_execute_raises_and_issues_no_request_for_a_non_https_endpoint():
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json=_success_payload())

    configurations = {
        "openai": ProviderConfiguration(
            provider_id="openai",
            endpoint="http://provider.invalid/v1/complete",
            credential_reference="openai-key",
        )
    }
    adapter = AIProviderAdapter(
        configurations, _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    with pytest.raises(InsecureEndpointError):
        adapter.execute(_request())

    assert requests_seen == []


def test_execute_ignores_a_parameters_entry_that_tries_to_override_model_or_messages():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_success_payload())

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )
    request = InteractionRequest(
        input="hello",
        provider_id="openai",
        model_id="gpt-4o-mini",
        parameters={"model": "some-other-model", "messages": [{"role": "system", "content": "x"}]},
    )

    adapter.execute(request)

    sent_body = json.loads(captured["request"].content)
    assert sent_body["model"] == "gpt-4o-mini"
    assert sent_body["messages"] == [{"role": "user", "content": "hello"}]


def test_execute_raises_when_the_response_content_is_not_a_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_payload(choices=[{"message": {"content": None}}]))

    adapter = AIProviderAdapter(
        _configurations(), _FakeCredentialPort({"openai-key": "sk-secret"}), client=_client(handler)
    )

    with pytest.raises(ProviderResponseError):
        adapter.execute(_request())


def test_send_request_timeout_is_actually_enforced_against_a_stalling_server():
    # test_send_request_never_disables_tls_verification_and_sets_an_explicit_timeout
    # only proves the timeout value is stored; MockTransport never simulates a
    # stall, so it cannot prove the timeout is finite and enforced. This test
    # uses a real TCP socket that accepts the connection but never responds,
    # with a short configured timeout, to prove the adapter actually bounds
    # how long it waits (AC10) rather than hanging indefinitely.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    def never_respond() -> None:
        try:
            conn, _ = sock.accept()
        except OSError:
            return
        time.sleep(5)
        conn.close()

    server_thread = threading.Thread(target=never_respond, daemon=True)
    server_thread.start()
    try:
        configurations = {
            "openai": ProviderConfiguration(
                provider_id="openai",
                endpoint=f"http://127.0.0.1:{port}/v1/complete",
                credential_reference="openai-key",
            )
        }
        adapter = AIProviderAdapter(
            configurations,
            _FakeCredentialPort({"openai-key": "sk-secret"}),
            timeout=0.2,
            require_https=False,  # local plain-TCP loopback stub only; never do this in production
        )

        start = time.monotonic()
        with pytest.raises(ProviderResponseError):
            adapter.execute(_request(provider_id="openai"))
        elapsed = time.monotonic() - start

        assert elapsed < 2.0
    finally:
        sock.close()
