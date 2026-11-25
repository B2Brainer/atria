"""The seven operations `api/` exposes over the JSON-RPC transport.

Per Increment 5 Scope/Expected Behavior: `initiate`, `get`, `list_by_cycle`,
and `list_cycles` delegate to the established `core/` operations without
altering their input/output shape (beyond `initiate`'s added `cycle_id`
sibling parameter). `set_credential`, `get_credential_status`, and
`remove_credential` are thin wrappers around the already-established
`CredentialPort` (`store()`/`get()`/`delete()`) — no new `core/ports/`
contract is introduced to support them. Every handler returns a JSON-safe
dict (via Pydantic's own `model_dump_json()`, round-tripped through
`json.loads()` to preserve `Decimal`/`UUID`/`datetime` fidelity exactly as
`adapters/persistence/adapter.py` already does) or raises — callers never see
a partially-serialized result.

No handler ever returns, logs, or raises an exception containing a resolved
secret value: `get_credential_status` may call the established
`CredentialPort.get()` internally to determine configured/not-configured and
derive a masked preview, but the retrieved secret itself never leaves this
module in a response, a masked form notwithstanding.
"""

from __future__ import annotations

import json
from uuid import UUID

from core.interaction.models import InteractionRequest

from api.composition import Composition

_UNMASKED_SUFFIX_LENGTH = 4


def _to_json(model) -> dict:
    return json.loads(model.model_dump_json())


def _mask(secret: str) -> str:
    if len(secret) <= _UNMASKED_SUFFIX_LENGTH:
        return "*" * len(secret)
    return f"{'*' * (len(secret) - _UNMASKED_SUFFIX_LENGTH)}{secret[-_UNMASKED_SUFFIX_LENGTH:]}"


class Handlers:
    def __init__(self, composition: Composition) -> None:
        self._composition = composition

    def initiate(self, request: dict, cycle_id: str) -> dict:
        interaction_request = InteractionRequest(**request)
        management = self._composition.interaction_management(UUID(cycle_id))
        record = management.initiate(interaction_request)
        return _to_json(record)

    def get(self, record_id: str) -> dict:
        record = self._composition.records.get(UUID(record_id))
        return _to_json(record)

    def list_by_cycle(self, cycle_id: str) -> list[dict]:
        records = self._composition.records.list_by_cycle(UUID(cycle_id))
        return [_to_json(record) for record in records]

    def list_cycles(self) -> list[str]:
        return [str(cycle_id) for cycle_id in self._composition.records.list_cycles()]

    def set_credential(self, provider_id: str, secret: str) -> dict:
        reference = self._provider_credential_reference(provider_id)
        self._composition.credentials.store(reference, secret)
        return {"success": True}

    def get_credential_status(self, provider_id: str) -> dict:
        reference = self._provider_credential_reference(provider_id)
        try:
            secret = self._composition.credentials.get(reference)
        except LookupError:
            return {"configured": False, "status": "not_configured", "masked_preview": None}
        return {"configured": True, "status": "configured", "masked_preview": _mask(secret)}

    def remove_credential(self, provider_id: str) -> dict:
        reference = self._provider_credential_reference(provider_id)
        try:
            self._composition.credentials.delete(reference)
        except LookupError:
            pass  # Already absent: removal is idempotent from the caller's perspective.
        return {"success": True}

    def _provider_credential_reference(self, provider_id: str) -> str:
        try:
            return self._composition.providers[provider_id].credential_reference
        except KeyError:
            raise KeyError(f"no ProviderConfiguration registered for {provider_id!r}") from None


OPERATIONS = (
    "initiate",
    "get",
    "list_by_cycle",
    "list_cycles",
    "set_credential",
    "get_credential_status",
    "remove_credential",
)


def dispatch_table(handlers: Handlers) -> dict[str, object]:
    # The single source of truth for "which bound method answers which RPC
    # method name" — OPERATIONS alone, never a second, independently
    # maintained literal (api/__main__.py and tests previously each kept
    # their own copy, which could silently drift from this list).
    return {name: getattr(handlers, name) for name in OPERATIONS}
