"""Sistema de uso de IA: única puerta de Atria hacia la IA (p1 §3)."""

from atria.domain import AIRequest, AIResult, Decision, InformationState
from atria.systems.ai.interface import AIProvider


class AISystem:
    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def execute(self, decision: Decision, state: InformationState) -> AIResult:
        """Construye la request desde la decisión y el estado y delega en el provider.

        Los `AIProviderError` del provider se propagan tal cual: ya son de Atria.
        """
        request = AIRequest(
            purpose=state.purpose.model_copy(), instruction=decision.instruction
        )
        return self._provider.complete(request)
