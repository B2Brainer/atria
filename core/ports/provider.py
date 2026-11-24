"""AIProviderPort — the boundary between the application core and an AI model provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.interaction.models import InteractionRequest, InteractionResult


class AIProviderPort(ABC):
    @abstractmethod
    def execute(self, request: InteractionRequest) -> InteractionResult:
        raise NotImplementedError
