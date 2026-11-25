"""PersistencePort — the boundary between the application core and interaction-record storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from core.records.models import InteractionRecord


class PersistencePort(ABC):
    @abstractmethod
    def save(self, record: InteractionRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, record_id: UUID) -> InteractionRecord:
        raise NotImplementedError

    @abstractmethod
    def list_by_cycle(self, cycle_id: UUID) -> list[InteractionRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_cycles(self) -> list[UUID]:
        raise NotImplementedError
