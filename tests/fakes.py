"""In-memory test doubles for the three core ports. No real adapter exists yet (Increments 3-4)."""

from uuid import UUID

from core.interaction.models import InteractionRequest, InteractionResult
from core.ports.credentials import CredentialPort
from core.ports.persistence import PersistencePort
from core.ports.provider import AIProviderPort
from core.records.models import InteractionRecord


class FakePersistencePort(PersistencePort):
    def __init__(self) -> None:
        self._records: dict[UUID, InteractionRecord] = {}
        self.save_calls: list[UUID] = []

    def save(self, record: InteractionRecord) -> None:
        self.save_calls.append(record.id)
        self._records[record.id] = record

    def get(self, record_id: UUID) -> InteractionRecord:
        return self._records[record_id]

    def list_by_cycle(self, cycle_id: UUID) -> list[InteractionRecord]:
        return [record for record in self._records.values() if record.cycle_id == cycle_id]


class FakeAIProviderPort(AIProviderPort):
    def __init__(self, result: InteractionResult, call_log: list[str] | None = None) -> None:
        self._result = result
        self._call_log = call_log if call_log is not None else []
        self.received_requests: list[InteractionRequest] = []

    def execute(self, request: InteractionRequest) -> InteractionResult:
        self._call_log.append("provider.execute")
        self.received_requests.append(request)
        return self._result


class FakeCredentialPort(CredentialPort):
    def __init__(self, call_log: list[str] | None = None) -> None:
        self._secrets: dict[str, str] = {}
        self._call_log = call_log if call_log is not None else []
        self.get_calls: list[str] = []

    def get(self, reference: str) -> str:
        self._call_log.append("credentials.get")
        self.get_calls.append(reference)
        return self._secrets.get(reference, "fake-secret")

    def store(self, reference: str, secret: str) -> None:
        self._secrets[reference] = secret

    def delete(self, reference: str) -> None:
        self._secrets.pop(reference, None)
