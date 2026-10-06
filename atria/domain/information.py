"""Propósito, información y conocimiento (p1 §3 "Sistema de información"; t1 §4).

El conocimiento aceptado no es un tipo aparte: es un `InformationItem` con estado
`ACCEPTED`. Así se conserva la distinción entre información y conocimiento sin
que un item pueda estar en dos colecciones a la vez.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Purpose(BaseModel):
    """Propósito de la sesión. Estructura mínima provisional (gap G5)."""

    text: NonEmptyStr


class EpistemicStatus(StrEnum):
    """Estado epistémico de un item. Lista provisional (gap G3)."""

    CONTEXT = "context"
    UNVERIFIED = "unverified"
    ACCEPTED = "accepted"


class Origin(StrEnum):
    USER = "user"
    AI = "ai"
    SYSTEM = "system"


class InformationItem(BaseModel):
    """Unidad de información. `iteration=0` indica que existe antes del ciclo."""

    id: NonEmptyStr
    content: NonEmptyStr
    status: EpistemicStatus
    origin: Origin
    iteration: int = Field(ge=0)


class OpenQuestion(BaseModel):
    id: NonEmptyStr
    text: NonEmptyStr
    resolved: bool = False


class InformationState(BaseModel):
    """Estado de información de una sesión.

    `items` es la información disponible (interpretación provisional de G3: es el
    superconjunto de contexto, información no verificada y conocimiento aceptado).
    Cada colección se obtiene filtrando por estado epistémico.
    """

    purpose: Purpose
    items: list[InformationItem] = []
    questions: list[OpenQuestion] = []

    @model_validator(mode="after")
    def _unique_ids(self) -> "InformationState":
        for name, ids in (
            ("items", [item.id for item in self.items]),
            ("questions", [question.id for question in self.questions]),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(f"ids duplicados en {name}")
        return self

    def _with_status(self, status: EpistemicStatus) -> list[InformationItem]:
        return [item for item in self.items if item.status == status]

    @property
    def context(self) -> list[InformationItem]:
        return self._with_status(EpistemicStatus.CONTEXT)

    @property
    def unverified(self) -> list[InformationItem]:
        return self._with_status(EpistemicStatus.UNVERIFIED)

    @property
    def accepted(self) -> list[InformationItem]:
        return self._with_status(EpistemicStatus.ACCEPTED)

    @property
    def open_questions(self) -> list[OpenQuestion]:
        return [question for question in self.questions if not question.resolved]
