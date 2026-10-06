"""Decisiones y evaluaciones del sistema de razonamiento (p1 §3)."""

from enum import StrEnum

from pydantic import BaseModel, model_validator

from atria.domain.information import InformationItem, NonEmptyStr, OpenQuestion


class ActionType(StrEnum):
    EXPLORE = "explore"
    ANSWER_QUESTION = "answer_question"
    VERIFY = "verify"


class Decision(BaseModel):
    """Siguiente paso elegido por el razonamiento."""

    action: ActionType
    instruction: NonEmptyStr


class ChangeKind(StrEnum):
    ADD_INFORMATION = "add_information"
    PROMOTE = "promote"
    REJECT = "reject"
    OPEN_QUESTION = "open_question"
    CLOSE_QUESTION = "close_question"


_PAYLOAD_BY_KIND = {
    ChangeKind.ADD_INFORMATION: "item",
    ChangeKind.OPEN_QUESTION: "question",
    ChangeKind.PROMOTE: "target_id",
    ChangeKind.REJECT: "target_id",
    ChangeKind.CLOSE_QUESTION: "target_id",
}


class StateChange(BaseModel):
    """Cambio propuesto sobre el estado. Lleva exactamente el payload de su `kind`."""

    kind: ChangeKind
    item: InformationItem | None = None
    question: OpenQuestion | None = None
    target_id: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> "StateChange":
        expected = _PAYLOAD_BY_KIND[self.kind]
        for name in ("item", "question", "target_id"):
            present = getattr(self, name) is not None
            if present != (name == expected):
                raise ValueError(f"'{self.kind}' requiere solo el campo '{expected}'")
        return self


class Verdict(StrEnum):
    """Veredicto sobre un resultado. Lista provisional (gap G1)."""

    ACCEPT = "accept"
    NEEDS_VALIDATION = "needs_validation"
    REJECT = "reject"


class Evaluation(BaseModel):
    verdict: Verdict
    changes: list[StateChange] = []
