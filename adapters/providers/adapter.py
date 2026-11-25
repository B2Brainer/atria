"""AIProviderAdapter — implements AIProviderPort against an external AI provider over HTTPS.

Public contract (per the Interfaces specification): ``execute()``.
``_prepare_provider_request()``, ``_send_request()``, and
``_normalize_response()`` are internal, invoked only from ``execute()``.

The authoritative documentation specifies no concrete third-party provider
API, so this increment settles on a single, fixed HTTP contract (Increment 4
Scope/Constraints) rather than a provider-agnostic abstraction: the OpenAI
Chat Completions wire shape (``POST {endpoint}`` with a ``{"model", "messages"}``
body, a ``{"choices": [{"message": {"content"}}], "usage"}`` response) — the
shape the acceptance-level test (criterion 13) exercises against the real
OpenAI API. ``ProviderConfiguration.endpoint`` is still fully configurable;
only the body/response shape is fixed to this one contract, not to an
OpenAI SDK.

OpenAI's response carries token counts but no monetary cost, so cost is
computed from ``PRICING_PER_MILLION_TOKENS`` (USD per 1,000,000 tokens),
keyed by the REQUESTED ``model_id`` — not the ``model`` OpenAI's response
echoes back, which is often a more specific, versioned string. A
``model_id`` absent from that table is treated the same as a response with
no usage data at all (``ExecutionMetrics`` stays ``None``) — cost cannot be
derived, so metrics as a whole are not fabricated.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from core.interaction.models import (
    ExecutionMetrics,
    InteractionRequest,
    InteractionResult,
    ProviderConfiguration,
)
from core.ports.credentials import CredentialPort
from core.ports.provider import AIProviderPort

DEFAULT_TIMEOUT = 30.0

# USD per 1,000,000 tokens. Public OpenAI pricing, recorded here only to
# derive ExecutionMetrics.cost from the token usage OpenAI's response
# actually reports; not an exhaustive or auto-updating price list.
PRICING_PER_MILLION_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}

# A production ProviderConfiguration.endpoint must be HTTPS; a bare local
# loopback host is the one universal, well-known exception (no real external
# AI provider is ever reachable at these hosts), so it needs no configurable
# flag — nothing a caller could misuse against a real endpoint.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class InsecureEndpointError(ValueError):
    """Raised when a ProviderConfiguration's endpoint is not HTTPS.

    The adapter authenticates with a Bearer credential; sending it to a
    non-HTTPS endpoint would transmit it in plaintext.
    """


class ProviderResponseError(RuntimeError):
    """Raised when the provider's HTTP response cannot be parsed into an InteractionResult.

    The message is deliberately redacted of the raw response body: a
    provider's error text can itself carry credential-derived content (e.g.
    OpenAI's own auth-failure responses echo a redacted key fragment, such as
    "Incorrect API key provided: sk-...1234"), and this message is what a
    caller's default exception logging would surface verbatim. The raw body
    is still available, for deliberate inspection only, via ``response_body``.
    """

    def __init__(self, message: str, *, response_body: str | None = None) -> None:
        super().__init__(message)
        self.response_body = response_body


class AIProviderAdapter(AIProviderPort):
    def __init__(
        self,
        providers: Mapping[str, ProviderConfiguration],
        credentials: CredentialPort,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._providers = providers
        self._credentials = credentials
        self._timeout = timeout
        # TLS certificate validation is httpx's default (verify=True) and is never
        # disabled here; an injected client (tests) carries its own transport but
        # still goes through this same, unmodified verification path.
        self._client = client if client is not None else httpx.Client()

    def execute(self, request: InteractionRequest) -> InteractionResult:
        prepared = self._prepare_provider_request(request)
        response = self._send_request(prepared)
        return self._normalize_response(response, request.model_id)

    def _prepare_provider_request(self, request: InteractionRequest) -> httpx.Request:
        try:
            configuration = self._providers[request.provider_id]
        except KeyError:
            raise KeyError(
                f"no ProviderConfiguration registered for {request.provider_id!r}"
            ) from None

        self._require_https_or_loopback(configuration.endpoint, request.provider_id)

        secret = self._credentials.get(configuration.credential_reference)

        # request.parameters is spread FIRST: model/messages are the adapter's
        # own, and must not be overridable by caller-supplied parameters.
        body = {
            **request.parameters,
            "model": request.model_id,
            "messages": [{"role": "user", "content": request.input}],
        }
        headers = {"Authorization": f"Bearer {secret}"}

        return self._client.build_request(
            "POST", configuration.endpoint, json=body, headers=headers, timeout=self._timeout
        )

    def _require_https_or_loopback(self, endpoint: str, provider_id: str) -> None:
        # The Bearer credential would otherwise go out in plaintext. The one
        # exemption is a local loopback host — no real external AI provider
        # is ever reachable there, so it's exempt by what it IS, not by a
        # configurable flag a production call site could misuse.
        parsed = urlsplit(endpoint)
        if parsed.scheme == "https":
            return
        if parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS:
            return
        raise InsecureEndpointError(
            f"ProviderConfiguration.endpoint for {provider_id!r} is not HTTPS "
            f"(and not a local loopback host): {endpoint!r}"
        )

    def _send_request(self, prepared_request: httpx.Request) -> httpx.Response:
        start = time.monotonic()
        error: ProviderResponseError | None = None
        try:
            response = self._client.send(prepared_request)
        except httpx.HTTPError as exc:
            # Built and raised OUTSIDE this except block (below): httpx sets
            # `.request` (headers included) on its own exceptions, so chaining
            # `exc` here (implicitly, via __context__, or via `from exc`) would
            # carry the Bearer credential as this exception's __cause__/__context__
            # — reachable by anything that introspects the exception chain, not
            # just its message.
            error = ProviderResponseError(f"provider request failed: {exc}")
        if error is not None:
            raise error
        duration = time.monotonic() - start

        if not response.is_success:
            raise ProviderResponseError(
                f"provider returned HTTP {response.status_code}", response_body=response.text
            )

        # Stashed on the response for _normalize_response(); httpx.Response
        # allows arbitrary attribute assignment and this keeps the duration
        # measurement colocated with the call it measures.
        response.extensions["atria_duration"] = duration
        return response

    def _normalize_response(self, response: httpx.Response, model_id: str) -> InteractionResult:
        # error/payload/output set inside the except/try below, then
        # raised/used AFTER it — same reasoning as _send_request: a
        # json.JSONDecodeError's .doc (or a UnicodeDecodeError's .object)
        # carries the full raw response body, so chaining the original
        # exception here (implicitly or via `from exc`) would put that body
        # on this exception's __cause__/__context__, not just a safe message.
        error: ProviderResponseError | None = None
        payload = output = None
        try:
            payload = response.json()
            output = payload["choices"][0]["message"]["content"]
            if not isinstance(output, str):
                raise TypeError(f"expected a string message content, got {type(output).__name__}")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            error = ProviderResponseError(f"provider response could not be parsed: {exc}")
        if error is not None:
            raise error

        metrics = self._derive_metrics(payload, response, model_id)
        return InteractionResult(output=output, status="success", metrics=metrics)

    def _derive_metrics(
        self, payload: dict, response: httpx.Response, model_id: str
    ) -> ExecutionMetrics | None:
        # Priced by the model_id THIS request asked for, not payload["model"]:
        # OpenAI's response often echoes a more specific, versioned model
        # string (e.g. "gpt-4o-mini-2024-07-18") that would never match a
        # pricing-table entry keyed by the configured alias.
        usage = payload.get("usage")
        pricing = PRICING_PER_MILLION_TOKENS.get(model_id)
        if usage is None or pricing is None:
            # No usage data, or a model this adapter has no pricing for: cost
            # cannot be derived, so metrics as a whole are left absent rather
            # than reporting a partial/fabricated ExecutionMetrics.
            return None

        error: ProviderResponseError | None = None
        input_tokens = output_tokens = None
        try:
            input_tokens = usage["prompt_tokens"]
            output_tokens = usage["completion_tokens"]
        except KeyError as exc:
            error = ProviderResponseError(
                f"provider response usage data could not be parsed: {exc}"
            )
        if error is not None:
            raise error

        input_price, output_price = pricing
        cost = (input_tokens * input_price + output_tokens * output_price) / Decimal(1_000_000)

        return ExecutionMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration=response.extensions["atria_duration"],
            cost=cost,
        )
