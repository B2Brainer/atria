"""Adaptador del proveedor inicial de IA: OpenAI (p1 §5).

Configuración desde el entorno (ver `.env.example`): `OPENAI_API_KEY`,
`ATRIA_AI_MODEL` y `ATRIA_AI_TIMEOUT` (segundos, 30 por defecto). Los errores del
SDK se traducen a `AIProviderError` / `AITimeoutError` con mensajes genéricos y sin
encadenar la excepción original, para que ningún texto del proveedor (que puede
repetir parte de la key) llegue a logs o trazas.
"""

import math
import os

import httpx2
import openai

from atria.domain import AIRequest, AIResult
from atria.systems.ai import AIProvider, AIProviderError, AITimeoutError

DEFAULT_TIMEOUT_SECONDS = 30.0


class AIConfigurationError(Exception):
    """Configuración del proveedor ausente o inválida. Nunca incluye su valor."""


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AIConfigurationError(f"falta la variable de entorno {name}")
    return value


def _timeout_from_env() -> float:
    raw = os.environ.get("ATRIA_AI_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError:
        timeout = 0.0
    if not (math.isfinite(timeout) and timeout > 0):
        raise AIConfigurationError(
            "ATRIA_AI_TIMEOUT debe ser un número de segundos mayor que 0"
        )
    return timeout


class OpenAIProvider(AIProvider):
    def __init__(self, http_client: httpx2.Client | None = None) -> None:
        api_key = _required_env("OPENAI_API_KEY")
        self._model = _required_env("ATRIA_AI_MODEL")
        # Sin reintentos del SDK: el timeout configurado es el límite real de la
        # llamada y cualquier reintento será una decisión visible de Atria.
        self._client = openai.OpenAI(
            api_key=api_key,
            timeout=_timeout_from_env(),
            max_retries=0,
            http_client=http_client,
        )

    def complete(self, request: AIRequest) -> AIResult:
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": f"Propósito: {request.purpose.text}"},
                    {"role": "user", "content": request.instruction},
                ],
            )
        except openai.APITimeoutError:
            raise AITimeoutError("el proveedor de IA no respondió a tiempo") from None
        except openai.APIStatusError as error:
            raise AIProviderError(
                f"el proveedor de IA respondió con estado {error.status_code}"
            ) from None
        except openai.OpenAIError:
            raise AIProviderError("fallo al llamar al proveedor de IA") from None

        content = completion.choices[0].message.content if completion.choices else None
        if content is None:
            raise AIProviderError(
                "el proveedor de IA devolvió una respuesta sin contenido"
            )
        return AIResult(content=content)
