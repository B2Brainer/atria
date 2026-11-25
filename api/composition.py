"""`api/`'s composition root — wires real adapters to the application core.

Per Increment 5's Expected Behavior item 1: a single, process-scoped
``InteractionRecordManagement`` and ``CredentialPort``/``AIProviderPort``
instance are constructed once; ``InteractionManagement`` is constructed per
active ``cycle_id`` as needed, not bound to one cycle for the process
lifetime. ``InteractionManagement``'s own constructor/signature is unchanged
from Increments 2-4.
"""

from __future__ import annotations

from uuid import UUID

from adapters.credentials.adapter import CredentialAdapter
from adapters.persistence.adapter import PersistenceAdapter
from adapters.providers.adapter import AIProviderAdapter
from core.interaction.operations import InteractionManagement
from core.records.operations import InteractionRecordManagement

from api import config


class Composition:
    def __init__(self) -> None:
        self.providers = config.load_providers()
        self.credentials = CredentialAdapter(service=config.keychain_service())
        self.persistence = PersistenceAdapter(config.db_path())
        self.provider_adapter = AIProviderAdapter(self.providers, self.credentials)
        self.records = InteractionRecordManagement(self.persistence)

    def interaction_management(self, cycle_id: UUID) -> InteractionManagement:
        # Cheap, stateless wiring over already-constructed adapters/mapping:
        # constructing one per call needs no caching to stay correct, and
        # avoids any shared mutable state between concurrently open cycles.
        return InteractionManagement(
            cycle_id,
            self.provider_adapter,
            self.credentials,
            self.records,
            self.providers,
        )
