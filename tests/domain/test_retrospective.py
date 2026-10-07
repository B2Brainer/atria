import pytest

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
    build_retrospective,
)

PURPOSE = Purpose(text="Entender el ciclo de Atria")
INITIAL = InformationState(purpose=PURPOSE)


def item(id: str, status: EpistemicStatus) -> InformationItem:
    return InformationItem(
        id=id, content=id, status=status, origin=Origin.AI, iteration=1
    )


FINAL = InformationState(
    purpose=PURPOSE,
    items=[
        item("ctx", EpistemicStatus.CONTEXT),
        item("a", EpistemicStatus.ACCEPTED),
        item("u", EpistemicStatus.UNVERIFIED),
        item("b", EpistemicStatus.ACCEPTED),
    ],
    questions=[
        OpenQuestion(id="q1", text="¿Abierta?"),
        OpenQuestion(id="q2", text="¿Resuelta?", resolved=True),
    ],
)


def trace(iteration: int, previous: InformationState, resulting: InformationState):
    change = StateChange(kind=ChangeKind.ADD_INFORMATION, item=resulting.items[-1])
    return IterationTrace(
        session_id="s1",
        iteration=iteration,
        previous_state=previous,
        decision=Decision(action=ActionType.EXPLORE, instruction=f"paso {iteration}"),
        ai_request=AIRequest(purpose=PURPOSE, instruction=f"paso {iteration}"),
        ai_result=AIResult(content="algo"),
        evaluation=Evaluation(verdict=Verdict.ACCEPT, changes=[change]),
        applied_changes=[change],
        resulting_state=resulting,
    )


TRACES = [trace(1, INITIAL, FINAL), trace(2, FINAL, FINAL)]


def finished(reason: FinishReason, state: InformationState = FINAL) -> Session:
    return Session(
        id="s1",
        purpose=PURPOSE,
        state=state,
        status=CycleStatus.FINISHED,
        finish_reason=reason,
    )


def test_retrospective_reflects_final_state_and_traces():
    retrospective = build_retrospective(finished(FinishReason.MAX_ITERATIONS), TRACES)

    assert retrospective.session_id == "s1"
    assert retrospective.purpose == PURPOSE
    assert retrospective.iterations == 2
    assert retrospective.finish_reason == FinishReason.MAX_ITERATIONS
    assert [i.id for i in retrospective.accepted_knowledge] == ["a", "b"]
    assert [i.id for i in retrospective.unverified] == ["u"]
    assert [q.id for q in retrospective.open_questions] == ["q1"]
    assert [(s.iteration, s.decision.instruction) for s in retrospective.summary] == [
        (1, "paso 1"),
        (2, "paso 2"),
    ]
    assert retrospective.summary[0].applied_changes == TRACES[0].applied_changes


def test_retrospective_is_deterministic():
    session = finished(FinishReason.PURPOSE_FULFILLED)

    first = build_retrospective(session, TRACES)
    second = build_retrospective(session, TRACES)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_retrospective_of_session_ended_by_error_without_iterations():
    retrospective = build_retrospective(finished(FinishReason.ERROR, INITIAL), [])

    assert retrospective.finish_reason == FinishReason.ERROR
    assert retrospective.iterations == 0
    assert retrospective.summary == []
    assert retrospective.accepted_knowledge == []


def test_retrospective_requires_finished_session():
    running = Session(id="s1", purpose=PURPOSE, state=FINAL)

    with pytest.raises(ValueError, match="no ha terminado"):
        build_retrospective(running, TRACES)


@pytest.mark.parametrize(
    ("traces", "message"),
    [
        ([TRACES[0].model_copy(update={"session_id": "otra"})], "no son de la sesión"),
        ([TRACES[1]], "consecutivas"),
        ([TRACES[1], TRACES[0]], "consecutivas"),
        (
            [trace(1, INITIAL, INITIAL.model_copy(update={"items": FINAL.items[:1]}))],
            "estado final",
        ),
    ],
)
def test_retrospective_rejects_traces_that_do_not_belong_to_the_session(
    traces, message
):
    with pytest.raises(ValueError, match=message):
        build_retrospective(finished(FinishReason.MAX_ITERATIONS), traces)
