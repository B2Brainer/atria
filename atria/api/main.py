"""Composition root de la API: cablea las implementaciones concretas desde el entorno.

`uv run uvicorn atria.api.main:app`. Variables (ver `.env.example`):
`ATRIA_DATABASE_URL`, las del proveedor de IA y `ATRIA_MAX_ITERATIONS` (10 por
defecto). Si falta o es inválida alguna, falla al arrancar con un mensaje claro y
sin valores secretos.
"""

import os

from atria.api.app import create_app
from atria.infrastructure.ai_providers.openai import OpenAIProvider
from atria.infrastructure.database import (
    PostgresInformationSystem,
    PostgresSessionStore,
    PostgresTraceRecorder,
    create_schema,
    engine_from_env,
)

DEFAULT_MAX_ITERATIONS = 10


class ConfigurationError(Exception):
    """Configuración de la API ausente o inválida."""


def max_iterations_from_env() -> int:
    raw = os.environ.get("ATRIA_MAX_ITERATIONS", "").strip()
    if not raw:
        return DEFAULT_MAX_ITERATIONS
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise ConfigurationError("ATRIA_MAX_ITERATIONS debe ser un entero mayor que 0")
    return value


def build_app():
    max_iterations = max_iterations_from_env()
    provider = OpenAIProvider()
    engine = engine_from_env()
    create_schema(engine)
    return create_app(
        information=PostgresInformationSystem(engine),
        trace=PostgresTraceRecorder(engine),
        sessions=PostgresSessionStore(engine),
        provider=provider,
        max_iterations=max_iterations,
    )


app = build_app()
