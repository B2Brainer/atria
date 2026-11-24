import sys
import uuid

import pytest

if sys.platform != "darwin":
    pytest.skip(
        "CredentialAdapter requires the macOS Security framework (darwin only); "
        "this is the documented non-macOS CI skip fallback (AGENTS.md).",
        allow_module_level=True,
    )

from adapters.credentials.adapter import CredentialAdapter, KeychainItemNotFoundError

TEST_SERVICE_PREFIX = "com.atria.credentials.test"


@pytest.fixture
def service():
    return f"{TEST_SERVICE_PREFIX}.{uuid.uuid4().hex[:8]}"


@pytest.fixture
def adapter(service):
    return CredentialAdapter(service=service)


@pytest.fixture
def cleanup(adapter):
    created: list[str] = []
    yield created
    for reference in created:
        try:
            adapter.delete(reference)
        except KeychainItemNotFoundError:
            pass  # already deleted by the test itself — expected, not a leak
