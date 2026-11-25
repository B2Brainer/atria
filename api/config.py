"""Static, injected configuration for `api/`'s composition.

Per Increment 4's settled resolution, ``ProviderConfiguration`` is static,
injected configuration — not persisted or dynamically looked up. This module
is the one place that configuration is assembled for the desktop application,
from environment variables (never hardcoded secrets; `endpoint`/`provider_id`
are not secret and may default sensibly).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from core.interaction.models import ProviderConfiguration

# The repository root: api/config.py -> api/ -> repo root. Used as the
# default database location so persistence (and therefore conversation
# history, per Increment 5's relaunch-persistence requirement) is not
# silently cwd-dependent — a desktop app launched from a different working
# directory than a prior run would otherwise open a different, "empty"
# database instead of the one holding its history.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# provider_id -> (default endpoint, env var overriding it). `credential_reference`
# is derived per provider_id, not independently configurable: it is purely an
# internal lookup key into CredentialPort, never a secret itself.
_DEFAULT_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
}


def credential_reference(provider_id: str) -> str:
    return f"atria.provider.{provider_id}"


def load_providers() -> Mapping[str, ProviderConfiguration]:
    providers: dict[str, ProviderConfiguration] = {}
    for provider_id, default_endpoint in _DEFAULT_ENDPOINTS.items():
        env_name = f"ATRIA_PROVIDER_{provider_id.upper()}_ENDPOINT"
        endpoint = os.environ.get(env_name, default_endpoint)
        providers[provider_id] = ProviderConfiguration(
            provider_id=provider_id,
            endpoint=endpoint,
            credential_reference=credential_reference(provider_id),
        )
    return providers


def db_path() -> str:
    return os.environ.get("ATRIA_DB_PATH", str(_REPO_ROOT / "atria.sqlite3"))


def keychain_service() -> str:
    return os.environ.get("ATRIA_KEYCHAIN_SERVICE", "com.atria.credentials")
