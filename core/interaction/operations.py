"""InteractionManagement — coordinates AI interactions.

Public contract (InteractionInterface, per the Interfaces specification):
``initiate()``. ``_prepare_clean_interaction()``, ``_select_provider()``, and
``_assemble_record()`` are internal operations (per the Detailed Behavior
specification), not part of the module's public contract.

An instance is scoped to a single ``AIUsageCycle`` (the cycle whose records
it assembles into); multiple clean interactions may be initiated against the
same cycle, each isolated from residual state carried by the previous ones.
"""

from uuid import UUID

from core.interaction.models import InteractionRequest, InteractionResult
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
    ) -> None:
        self._cycle_id = cycle_id
        self._provider = provider
        self._credentials = credentials
        self._records = records

    def initiate(self, request: InteractionRequest) -> InteractionRecord:
        clean_request = self._prepare_clean_interaction(request)
        self._select_provider(clean_request)
        result = self._provider.execute(clean_request)
        return self._assemble_record(clean_request, result)

    def _prepare_clean_interaction(self, request: InteractionRequest) -> InteractionRequest:
        return request.model_copy(deep=True)

    def _select_provider(self, request: InteractionRequest) -> str:
        # The resolved credential is not passed on to AIProviderPort.execute(): the
        # Interfaces specification's execute(request) takes no credential parameter.
        # How a resolved secret reaches the provider call is an adapter-contract
        # question deferred to Increments 3/4; this increment only has to establish
        # that the credential lookup happens before provider invocation (AC4).
        return self._credentials.get(request.provider_id)

    def _assemble_record(
        self, request: InteractionRequest, result: InteractionResult
    ) -> InteractionRecord:
        sequence = self._records._assign_sequence(self._cycle_id)
        record = InteractionRecord(
            cycle_id=self._cycle_id, sequence=sequence, request=request, result=result
        )
        self._records._register_interaction(record)
        return record
