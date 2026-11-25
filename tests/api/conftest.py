import sys
import uuid

import pytest

if sys.platform != "darwin":
    pytest.skip(
        "api/'s composition wires a real CredentialAdapter, which requires the "
        "macOS Security framework (darwin only); this is the documented "
        "non-macOS CI skip fallback (AGENTS.md).",
        allow_module_level=True,
    )

from api.composition import Composition
from api.handlers import Handlers


@pytest.fixture
def composition(tmp_path, monkeypatch):
    monkeypatch.setenv("ATRIA_DB_PATH", str(tmp_path / "atria.sqlite3"))
    monkeypatch.setenv(
        "ATRIA_KEYCHAIN_SERVICE", f"com.atria.credentials.test.{uuid.uuid4().hex[:8]}"
    )
    composition = Composition()
    yield composition
    for provider_id in composition.providers:
        try:
            composition.credentials.delete(composition.providers[provider_id].credential_reference)
        except LookupError:
            pass


@pytest.fixture
def handlers(composition):
    return Handlers(composition)
