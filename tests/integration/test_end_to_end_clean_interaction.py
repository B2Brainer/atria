"""Acceptance criterion 13: a full Clean Interaction against the real OpenAI API.

This is this increment's acceptance-level evidence, executed against the real
OpenAI API with a real, operator-supplied API key, retrieved through a real
CredentialAdapter and persisted through a real PersistenceAdapter — per
Increment 4's Verification section, it is not required to run unattended in
CI (it depends on a live, costed, rate-limited external service and a
provisioned credential), but must be executed and its result captured at
least once as reported verification evidence.

Skips (not a failure) when:
- not running on macOS (CredentialAdapter, per Increment 3, is darwin-only).
- ATRIA_TEST_OPENAI_API_KEY is not set in the environment — the operator
  supplies a real key out-of-band; this test never embeds one in source.
"""

import os
import sys
import uuid

import pytest

API_KEY = os.environ.get("ATRIA_TEST_OPENAI_API_KEY")

if sys.platform != "darwin" or not API_KEY:
    pytest.skip(
        "requires macOS (CredentialAdapter is darwin-only, per AGENTS.md) and "
        "ATRIA_TEST_OPENAI_API_KEY (an operator-supplied real OpenAI API key for "
        "this acceptance-level evidence, not run unattended in CI).",
        allow_module_level=True,
    )

from adapters.credentials.adapter import CredentialAdapter  # noqa: E402
from adapters.persistence.adapter import PersistenceAdapter  # noqa: E402
from adapters.providers.adapter import AIProviderAdapter  # noqa: E402
from core.interaction.models import InteractionRequest, ProviderConfiguration  # noqa: E402
from core.interaction.operations import InteractionManagement  # noqa: E402
from core.records.operations import InteractionRecordManagement  # noqa: E402

OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
CREDENTIAL_REFERENCE = "openai-acceptance-test"


def test_initiate_executes_against_the_real_openai_api_and_persists_the_record(tmp_path):
    service = f"com.atria.credentials.test.{uuid.uuid4().hex[:8]}"
    credentials = CredentialAdapter(service=service)
    credentials.store(CREDENTIAL_REFERENCE, API_KEY)
    try:
        persistence = PersistenceAdapter(str(tmp_path / "atria.sqlite3"))
        records = InteractionRecordManagement(persistence)
        providers = {
            "openai": ProviderConfiguration(
                provider_id="openai",
                endpoint=OPENAI_ENDPOINT,
                credential_reference=CREDENTIAL_REFERENCE,
            )
        }
        provider_adapter = AIProviderAdapter(providers, credentials)
        interaction = InteractionManagement(
            uuid.uuid4(), provider_adapter, credentials, records, providers
        )
        request = InteractionRequest(
            input="Reply with exactly the word: pong",
            provider_id="openai",
            model_id="gpt-4o-mini",
            parameters={"max_tokens": 5},
        )

        record = interaction.initiate(request)

        assert record.request == request
        assert record.result.output

        retrieved = records.get(record.id)
        assert retrieved == record

        secret_fragment = API_KEY[-8:]
        for value in (str(record), str(retrieved)):
            assert secret_fragment not in value
    finally:
        credentials.delete(CREDENTIAL_REFERENCE)
