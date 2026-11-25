"""InteractionManagement — coordinates AI interactions.

Public contract (InteractionInterface, per the Interfaces specification):
``initiate()``. ``_prepare_clean_interaction()``, ``_select_provider()``, and
``_assemble_record()`` are internal operations (per the Detailed Behavior
specification), not part of the module's public contract.

An instance is scoped to a single ``AIUsageCycle`` (the cycle whose records
it assembles into); multiple clean interactions may be initiated against the
same cycle, each isolated from residual state carried by the previous ones.
"""

from collections.abc import Mapping
from uuid import UUID

from core.interaction.models import InteractionRequest, InteractionResult, ProviderConfiguration
from core.ports.credentials import CredentialPort
from core.ports.provider import AIProviderPort
from core.records.models import InteractionRecord
from core.records.operations import InteractionRecordManagement


class InteractionManagement:
    def __init__(
        self,
        cycle_id: UUID,
        provider: AIProviderPort,
        credentials: CredentialPort,
        records: InteractionRecordManagement,
        providers: Mapping[str, ProviderConfiguration],
    ) -> None:
        self._cycle_id = cycle_id
        self._provider = provider
        self._credentials = credentials
        self._records = records
        self._providers = providers

    def initiate(self, request: InteractionRequest) -> InteractionRecord:
        clean_request = self._prepare_clean_interaction(request)
        self._select_provider(clean_request)
        result = self._provider.execute(clean_request)
        return self._assemble_record(clean_request, result)

    def _prepare_clean_interaction(self, request: InteractionRequest) -> InteractionRequest:
        return request.model_copy(deep=True)

    def _select_provider(self, request: InteractionRequest) -> str:
        # Fail-fast ahead of AIProviderPort.execute(): resolve the configured
        # provider and confirm its credential is retrievable before the provider
        # call is ever made (Increment 4 AC11/AC12). The resolved credential is
        # not passed on to execute(): the Interfaces specification's
        # execute(request) takes no credential parameter — AIProviderAdapter
        # resolves it again itself via its own injected CredentialPort
        # (Increment 4's settled credential-delivery decision).
        try:
            configuration = self._providers[request.provider_id]
        except KeyError:
            raise KeyError(f"no ProviderConfiguration registered for {request.provider_id!r}")
        return self._credentials.get(configuration.credential_reference)

    def _assemble_record(
        self, request: InteractionRequest, result: InteractionResult
    ) -> InteractionRecord:
        sequence = self._records._assign_sequence(self._cycle_id)
        record = InteractionRecord(
            cycle_id=self._cycle_id, sequence=sequence, request=request, result=result
        )
        self._records._register_interaction(record)
        return record
