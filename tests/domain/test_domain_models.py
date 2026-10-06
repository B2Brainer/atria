from datetime import datetime

import pytest
from pydantic import ValidationError

from atria.domain import (
    ActionType,
    AIRequest,
    AIResult,
    ChangeKind,
    CycleStatus,
    Decision,
    EpistemicStatus,
    Evaluation,
    FinishReason,
    InformationItem,
    InformationState,
    IterationTrace,
    OpenQuestion,
    Origin,
    Purpose,
    Session,
    StateChange,
    Verdict,
)

PURPOSE = Purpose(text="Entender el ciclo de Atria")


def item(id: str, status: EpistemicStatus) -> InformationItem:
    return InformationItem(
        id=id, content=f"contenido {id}", status=status, origin=Origin.AI, iteration=1
    )


UNVERIFIED = item("i1", EpistemicStatus.UNVERIFIED)
ACCEPTED = item("i2", EpistemicStatus.ACCEPTED)
QUESTION = OpenQuestion(id="q1", text="¿Qué es un propósito?")
STATE = InformationState(
    purpose=PURPOSE,
    items=[item("c1", EpistemicStatus.CONTEXT), UNVERIFIED, ACCEPTED],
    questions=[QUESTION, OpenQuestion(id="q2", text="¿Cerrada?", resolved=True)],
)
DECISION = Decision(action=ActionType.EXPLORE, instruction="Explora el propósito")
REQUEST = AIRequest(purpose=PURPOSE, instruction="Explora el propósito")
RESULT = AIResult(content="respuesta")
CHANGES = [
    StateChange(kind=ChangeKind.ADD_INFORMATION, item=UNVERIFIED),
    StateChange(kind=ChangeKind.PROMOTE, target_id="i1"),
    StateChange(kind=ChangeKind.REJECT, target_id="i1"),
    StateChange(kind=ChangeKind.OPEN_QUESTION, question=QUESTION),
    StateChange(kind=ChangeKind.CLOSE_QUESTION, target_id="q1"),
]
EVALUATION = Evaluation(verdict=Verdict.NEEDS_VALIDATION, changes=CHANGES)
TRACE_FIELDS = {
    "session_id": "s1",
    "iteration": 1,
    "previous_state": STATE,
    "decision": DECISION,
    "ai_request": REQUEST,
    "ai_result": RESULT,
    "evaluation": EVALUATION,
    "applied_changes": CHANGES,
    "resulting_state": STATE,
}


@pytest.mark.parametrize("text", ["", "   "])
def test_purpose_rejects_blank_text(text):
    with pytest.raises(ValidationError):
        Purpose(text=text)


def test_purpose_strips_whitespace():
    assert Purpose(text="  x ").text == "x"


def test_information_item_rejects_unknown_status():
    with pytest.raises(ValidationError):
        InformationItem(
            id="i", content="c", status="refuted", origin=Origin.USER, iteration=0
        )


def test_state_separates_unverified_from_accepted():
    state = InformationState(purpose=PURPOSE, items=[UNVERIFIED, ACCEPTED])

    assert state.unverified == [UNVERIFIED]
    assert state.accepted == [ACCEPTED]
    assert state.context == []


def test_state_open_questions_excludes_resolved():
    assert STATE.open_questions == [QUESTION]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"items": [UNVERIFIED, UNVERIFIED]},
        {"questions": [QUESTION, QUESTION]},
    ],
)
def test_state_rejects_duplicate_ids(kwargs):
    with pytest.raises(ValidationError):
        InformationState(purpose=PURPOSE, **kwargs)


def test_iteration_trace_accepts_all_fields():
    IterationTrace(**TRACE_FIELDS)


@pytest.mark.parametrize("missing", TRACE_FIELDS)
def test_iteration_trace_requires_each_field(missing):
    fields = {k: v for k, v in TRACE_FIELDS.items() if k != missing}
    with pytest.raises(ValidationError):
        IterationTrace(**fields)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iteration": 0},
        {"session_id": " "},
        {"timestamp": datetime(2026, 1, 1)},  # noqa: DTZ001 — sin zona: se rechaza
    ],
)
def test_iteration_trace_rejects_invalid_identity(kwargs):
    with pytest.raises(ValidationError):
        IterationTrace(**(TRACE_FIELDS | kwargs))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": ChangeKind.ADD_INFORMATION},
        {"kind": ChangeKind.ADD_INFORMATION, "item": UNVERIFIED, "target_id": "i1"},
        {"kind": ChangeKind.PROMOTE},
        {"kind": ChangeKind.PROMOTE, "item": UNVERIFIED},
        {"kind": ChangeKind.OPEN_QUESTION, "target_id": "q1"},
        {"kind": ChangeKind.CLOSE_QUESTION, "question": QUESTION},
    ],
)
def test_state_change_payload_must_match_kind(kwargs):
    with pytest.raises(ValidationError):
        StateChange(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": CycleStatus.FINISHED},
        {"finish_reason": FinishReason.ERROR},
        {"purpose": Purpose(text="Otro propósito")},
    ],
)
def test_session_rejects_inconsistent_state(kwargs):
    fields = {"id": "s1", "purpose": PURPOSE, "state": STATE} | kwargs
    with pytest.raises(ValidationError):
        Session(**fields)


@pytest.mark.parametrize(
    "model",
    [
        PURPOSE,
        UNVERIFIED,
        QUESTION,
        STATE,
        DECISION,
        REQUEST,
        RESULT,
        EVALUATION,
        *CHANGES,
        IterationTrace(**TRACE_FIELDS),
        Session(id="s1", purpose=PURPOSE, state=STATE),
        Session(
            id="s2",
            purpose=PURPOSE,
            state=STATE,
            status=CycleStatus.FINISHED,
            finish_reason=FinishReason.PURPOSE_FULFILLED,
        ),
    ],
)
def test_json_round_trip(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model
