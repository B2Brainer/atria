import pytest
from pydantic import ValidationError

from atria.domain import (
    ActionType,
    AIRequest,
    AIResult,
    ChangeKind,
    Decision,
    EpistemicStatus,
    Evaluation,
    InformationItem,
    InformationState,
    IterationTrace,
    Origin,
    Purpose,
    StateChange,
    Verdict,
)
from atria.infrastructure.database import PostgresTraceRecorder
from atria.systems.trace import InMemoryTraceRecorder, TraceError, TraceRecorder

PURPOSE = Purpose(text="Entender el ciclo de Atria")
ITEM = InformationItem(
    id="ai-1",
    content="El ciclo itera",
    status=EpistemicStatus.UNVERIFIED,
    origin=Origin.AI,
    iteration=1,
)
CHANGES = [StateChange(kind=ChangeKind.ADD_INFORMATION, item=ITEM)]
DECISION = Decision(action=ActionType.EXPLORE, instruction="Explora el propósito")
SEVEN_FIELDS = {
    "previous_state": InformationState(purpose=PURPOSE),
    "decision": DECISION,
    "ai_request": AIRequest(purpose=PURPOSE, instruction=DECISION.instruction),
    "ai_result": AIResult(content="El ciclo itera"),
    "evaluation": Evaluation(verdict=Verdict.NEEDS_VALIDATION, changes=CHANGES),
    "applied_changes": CHANGES,
    "resulting_state": InformationState(purpose=PURPOSE, items=[ITEM]),
}


def trace(iteration: int, session_id: str = "s1") -> IterationTrace:
    return IterationTrace(session_id=session_id, iteration=iteration, **SEVEN_FIELDS)


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
def recorder(request) -> TraceRecorder:
    if request.param == "postgres":
        return PostgresTraceRecorder(request.getfixturevalue("pg_engine"))
    return InMemoryTraceRecorder()


def test_in_memory_implements_interface():
    assert isinstance(InMemoryTraceRecorder(), TraceRecorder)


def test_list_returns_traces_in_iteration_order(recorder):
    traces = [trace(1), trace(2), trace(3)]
    for t in traces:
        recorder.record(t)

    assert recorder.list("s1") == traces
    assert [t.iteration for t in recorder.list("s1")] == [1, 2, 3]


def test_unknown_session_has_no_traces(recorder):
    assert recorder.list("nadie") == []


@pytest.mark.parametrize("missing", SEVEN_FIELDS)
def test_trace_missing_a_field_cannot_be_built(missing):
    fields = {k: v for k, v in SEVEN_FIELDS.items() if k != missing}
    with pytest.raises(ValidationError):
        IterationTrace(session_id="s1", iteration=1, **fields)


@pytest.mark.parametrize("missing", SEVEN_FIELDS)
def test_trace_missing_a_field_cannot_be_recorded(recorder, missing):
    fields = {k: v for k, v in SEVEN_FIELDS.items() if k != missing}
    unvalidated = IterationTrace.model_construct(session_id="s1", iteration=1, **fields)

    with pytest.raises(ValidationError):
        recorder.record(unvalidated)
    assert recorder.list("s1") == []


@pytest.mark.parametrize("field", SEVEN_FIELDS)
def test_trace_emptied_after_construction_cannot_be_recorded(recorder, field):
    invalid = trace(1)
    setattr(invalid, field, None)

    with pytest.raises(ValidationError):
        recorder.record(invalid)
    assert recorder.list("s1") == []


@pytest.mark.parametrize(
    ("recorded", "next_iteration"),
    [((), 2), ((1,), 1), ((1, 2), 1), ((1,), 3)],
    ids=["first-not-one", "duplicate", "past", "gap"],
)
def test_out_of_sequence_iteration_is_rejected(recorder, recorded, next_iteration):
    for iteration in recorded:
        recorder.record(trace(iteration))
    before = recorder.list("s1")

    with pytest.raises(TraceError):
        recorder.record(trace(next_iteration))
    assert recorder.list("s1") == before


def test_failed_record_does_not_block_the_correct_next_iteration(recorder):
    recorder.record(trace(1))
    with pytest.raises(TraceError):
        recorder.record(trace(3))

    recorder.record(trace(2))
    assert [t.iteration for t in recorder.list("s1")] == [1, 2]


def test_mutating_listed_traces_does_not_alter_storage(recorder):
    original = trace(1)
    recorder.record(original)

    listed = recorder.list("s1")
    listed[0].resulting_state.items.clear()
    listed[0].decision.instruction = "otra"
    listed[0].iteration = 7
    listed.append(trace(2))

    assert recorder.list("s1") == [original]


def test_mutating_the_recorded_object_does_not_alter_storage(recorder):
    original = trace(1)
    recorder.record(original)
    expected = original.model_copy(deep=True)

    original.resulting_state.items.clear()
    original.applied_changes.append(CHANGES[0])

    assert recorder.list("s1") == [expected]


def test_sessions_are_isolated(recorder):
    s1 = [trace(1, "s1"), trace(2, "s1")]
    s2 = trace(1, "s2")
    recorder.record(s1[0])
    recorder.record(s2)
    recorder.record(s1[1])

    assert recorder.list("s1") == s1
    assert recorder.list("s2") == [s2]
    with pytest.raises(TraceError):
        recorder.record(trace(3, "s2"))
