"""Sistema de uso de IA: única puerta de Atria hacia la IA (p1 §3)."""

from atria.domain import AIRequest, AIResult, Decision, InformationState
from atria.systems.ai.interface import AIProvider


class AISystem:
    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def build_request(self, decision: Decision, state: InformationState) -> AIRequest:
        """La request que `execute` envía para esta decisión y este estado."""
        return AIRequest(
            purpose=state.purpose.model_copy(), instruction=decision.instruction
        )

    def execute(self, decision: Decision, state: InformationState) -> AIResult:
        """Construye la request desde la decisión y el estado y delega en el provider.

        Los `AIProviderError` del provider se propagan tal cual: ya son de Atria.
        """
        return self._provider.complete(self.build_request(decision, state))
