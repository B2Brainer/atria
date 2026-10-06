"""Puerto hacia los proveedores de IA y errores propios de Atria (p1 §2, §5).

Contrato: un `AIProvider` solo lanza `AIProviderError` (o subclases). El adaptador
de cada proveedor traduce los errores de su SDK a estos tipos, de modo que ningún
tipo del proveedor sale de `atria/infrastructure/ai_providers/`.
"""

from abc import ABC, abstractmethod

from atria.domain import AIRequest, AIResult


class AIProviderError(Exception):
    """Fallo del proveedor de IA, expresado como error de Atria."""


class AITimeoutError(AIProviderError):
    """El proveedor de IA no respondió a tiempo."""


class AIProvider(ABC):
    @abstractmethod
    def complete(self, request: AIRequest) -> AIResult:
        """Ejecuta la request. Si falla, lanza `AIProviderError`."""
