"""Entrada y salida del sistema de uso de IA, sin tipos de proveedor (p1 §5)."""

from pydantic import BaseModel

from atria.domain.information import NonEmptyStr, Purpose


class AIRequest(BaseModel):
    purpose: Purpose
    instruction: NonEmptyStr


class AIResult(BaseModel):
    content: str
