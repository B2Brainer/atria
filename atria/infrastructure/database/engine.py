"""Conexión a PostgreSQL desde el entorno (p1 §5).

La URL sale de `ATRIA_DATABASE_URL` (ver `.env.example`), con el formato
`postgresql+psycopg://usuario:contraseña@host:puerto/base`. Los errores de
configuración nunca incluyen la URL: puede llevar la contraseña.

Esquema v0: `create_schema` crea las tablas que falten (`metadata.create_all`). No
migra esquemas existentes; cuando haga falta migrar datos reales se adoptará una
herramienta de migraciones (p1 §8).
"""

import os

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.exc import ArgumentError

from atria.infrastructure.database.tables import metadata

URL_VARIABLE = "ATRIA_DATABASE_URL"


class DatabaseConfigurationError(Exception):
    """Configuración de la base de datos ausente o inválida. Nunca incluye su valor."""


def engine_from_url(raw: str, variable: str = URL_VARIABLE) -> Engine:
    """Crea el engine; no conecta hasta la primera operación."""
    if not raw.strip():
        raise DatabaseConfigurationError(f"falta la variable de entorno {variable}")
    try:
        url = make_url(raw.strip())
    except (ArgumentError, ValueError):
        # Sin encadenar: el mensaje de SQLAlchemy repite la URL, contraseña incluida
        # (`ValueError` sale, p. ej., de un puerto no numérico).
        raise DatabaseConfigurationError(f"{variable} no es una URL válida") from None
    if url.get_backend_name() != "postgresql":
        raise DatabaseConfigurationError(f"{variable} debe apuntar a PostgreSQL")
    return create_engine(url)


def engine_from_env() -> Engine:
    return engine_from_url(os.environ.get(URL_VARIABLE, ""))


def create_schema(engine: Engine) -> None:
    metadata.create_all(engine)
