"""InteractionRecordManagement — manages interaction records independently of providers.

Public contract (RecordInterface, per the Interfaces specification): ``get()``
and ``list_by_cycle()``. ``_assign_sequence()``, ``_register_interaction()``,
and ``_reconstruct_conversation()`` are internal collaboration operations (per
the Detailed Behavior specification) used by this component and by
``InteractionManagement``; they are not part of the module's public contract.
"""

from uuid import UUID

from core.ports.persistence import PersistencePort
from core.records.models import InteractionRecord


class InteractionRecordManagement:
    def __init__(self, persistence: PersistencePort) -> None:
        self._persistence = persistence

    def _assign_sequence(self, cycle_id: UUID) -> int:
        existing = self._persistence.list_by_cycle(cycle_id)
        if not existing:
            return 1
        return max(record.sequence for record in existing) + 1

    def _register_interaction(self, record: InteractionRecord) -> None:
        self._persistence.save(record)

    def get(self, record_id: UUID) -> InteractionRecord:
        return self._persistence.get(record_id)

    def list_by_cycle(self, cycle_id: UUID) -> list[InteractionRecord]:
        records = self._persistence.list_by_cycle(cycle_id)
        return self._reconstruct_conversation(records)

    def _reconstruct_conversation(
        self, records: list[InteractionRecord]
    ) -> list[InteractionRecord]:
        return sorted(records, key=lambda record: record.sequence)
