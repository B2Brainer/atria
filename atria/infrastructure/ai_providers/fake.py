"""Proveedor de IA determinista con respuestas guionizadas, para ejecutar el ciclo
sin red. Cada llamada consume el siguiente paso del guion: un `str` se devuelve
como contenido y un `AIProviderError` se lanza.
"""

from atria.domain import AIRequest, AIResult
from atria.systems.ai import AIProvider, AIProviderError


class FakeProvider(AIProvider):
    def __init__(self, script: list[str | AIProviderError]) -> None:
        self._script = list(script)
        self._next = 0
        self.requests: list[AIRequest] = []

    def complete(self, request: AIRequest) -> AIResult:
        self.requests.append(request.model_copy(deep=True))
        if self._next >= len(self._script):
            raise AIProviderError("el guion del FakeProvider no tiene más respuestas")
        step = self._script[self._next]
        self._next += 1
        if isinstance(step, AIProviderError):
            raise step
        return AIResult(content=step)
