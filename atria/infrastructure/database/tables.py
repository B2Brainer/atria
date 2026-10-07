"""Esquema relacional de Atria (p1 §5).

Tablas relacionales para las entidades estables (sesión, item de información,
iteración) y JSONB para lo que sigue evolucionando: las preguntas abiertas y el
contenido de las trazas. El conocimiento aceptado es un item con estado `accepted`
y se guarda por sesión (gap G7).
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

session = Table(
    "session",
    metadata,
    Column("id", String, primary_key=True),
    Column("purpose", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("finish_reason", String, nullable=True),
    Column("questions", JSONB, nullable=False),
    CheckConstraint(
        "(status = 'finished') = (finish_reason IS NOT NULL)",
        name="session_finish_reason_iff_finished",
    ),
)

information_item = Table(
    "information_item",
    metadata,
    Column(
        "session_id",
        String,
        ForeignKey("session.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("id", String, primary_key=True),
    Column("position", Integer, nullable=False),
    Column("content", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("origin", String, nullable=False),
    Column("iteration", Integer, nullable=False),
)

# Sin FK a `session`: el contrato de `TraceRecorder` no exige que la sesión exista.
iteration = Table(
    "iteration",
    metadata,
    Column("session_id", String, primary_key=True),
    Column("iteration", Integer, primary_key=True),
    Column("data", JSONB, nullable=False),
)
