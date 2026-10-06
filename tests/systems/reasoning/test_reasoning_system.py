import pytest

from atria.domain import (
    ActionType,
    AIRequest,
    AIResult,
    ChangeKind,
    EpistemicStatus,
    FinishReason,
    InformationItem,
    InformationState,
    IterationTrace,
    OpenQuestion,
    Origin,
    Purpose,
    StateChange,
    Verdict,
)
from atria.systems.information import InMemoryInformationSystem
from atria.systems.reasoning import ReasoningSystem

PURPOSE = Purpose(text="Entender el ciclo de Atria")
EMPTY = InformationState(purpose=PURPOSE)


def item(
    id: str,
    content: str,
    status: EpistemicStatus = EpistemicStatus.UNVERIFIED,
    iteration: int = 1,
) -> InformationItem:
    return InformationItem(
        id=id, content=content, status=status, origin=Origin.AI, iteration=iteration
    )


def state(*items: InformationItem, questions: list[OpenQuestion] = ()):
    return InformationState(purpose=PURPOSE, items=list(items), questions=questions)


def trace() -> IterationTrace:
    reasoning = ReasoningSystem(max_iterations=1)
    decision = reasoning.next_step(EMPTY)
    result = AIResult(content="algo")
    evaluation = reasoning.evaluate(EMPTY, result, iteration=1)
    return IterationTrace(
        previous_state=EMPTY,
        decision=decision,
        ai_request=AIRequest(purpose=PURPOSE, instruction=decision.instruction),
        ai_result=result,
        evaluation=evaluation,
        applied_changes=evaluation.changes,
        resulting_state=EMPTY,
    )


@pytest.fixture
def reasoning() -> ReasoningSystem:
    return ReasoningSystem(max_iterations=3)


# next_step


def test_next_step_on_empty_state_explores_with_purpose(reasoning):
    decision = reasoning.next_step(EMPTY)

    assert decision.action == ActionType.EXPLORE
    assert PURPOSE.text in decision.instruction


def test_next_step_prioritizes_first_open_question(reasoning):
    questions = [
        OpenQuestion(id="q1", text="¿resuelta?", resolved=True),
        OpenQuestion(id="q2", text="¿qué es una iteración?"),
        OpenQuestion(id="q3", text="¿otra?"),
    ]
    seeded = state(item("i1", "dato"), questions=questions)

    decision = reasoning.next_step(seeded)

    assert decision.action == ActionType.ANSWER_QUESTION
    assert "¿qué es una iteración?" in decision.instruction
    assert PURPOSE.text in decision.instruction


def test_next_step_verifies_unverified_information(reasoning):
    decision = reasoning.next_step(state(item("i1", "El ciclo itera")))

    assert decision.action == ActionType.VERIFY
    assert "El ciclo itera" in decision.instruction


def test_next_step_explores_when_only_accepted(reasoning):
    seeded = state(item("i1", "dato", EpistemicStatus.ACCEPTED))

    assert reasoning.next_step(seeded).action == ActionType.EXPLORE


# evaluate


def test_evaluate_adds_new_information_as_unverified(reasoning):
    evaluation = reasoning.evaluate(EMPTY, AIResult(content=" El ciclo itera "), 2)

    assert evaluation.verdict == Verdict.ACCEPT
    assert evaluation.changes == [
        StateChange(
            kind=ChangeKind.ADD_INFORMATION,
            item=item("ai-2", "El ciclo itera", iteration=2),
        )
    ]


def test_evaluate_promotes_repeated_unverified_information(reasoning):
    seeded = state(item("ai-1", "El ciclo itera."))

    evaluation = reasoning.evaluate(seeded, AIResult(content="el ciclo ITERA"), 2)

    assert evaluation.verdict == Verdict.ACCEPT
    assert evaluation.changes == [
        StateChange(kind=ChangeKind.PROMOTE, target_id="ai-1")
    ]


def test_evaluate_without_promotion_never_promotes():
    reasoning = ReasoningSystem(max_iterations=3, promote_on_repetition=False)
    seeded = state(item("ai-1", "El ciclo itera"))

    evaluation = reasoning.evaluate(seeded, AIResult(content="El ciclo itera"), 2)

    assert evaluation.changes == []


def test_evaluate_ignores_already_known_information(reasoning):
    seeded = state(item("c1", "El ciclo itera", EpistemicStatus.CONTEXT, 0))

    evaluation = reasoning.evaluate(seeded, AIResult(content="El ciclo itera"), 1)

    assert evaluation.verdict == Verdict.ACCEPT
    assert evaluation.changes == []


def test_evaluate_flags_contradiction_with_accepted_knowledge(reasoning):
    seeded = state(item("k1", "El ciclo itera", EpistemicStatus.ACCEPTED, 0))

    evaluation = reasoning.evaluate(seeded, AIResult(content="El ciclo no itera"), 1)

    assert evaluation.verdict == Verdict.NEEDS_VALIDATION
    kinds = [change.kind for change in evaluation.changes]
    assert kinds == [ChangeKind.ADD_INFORMATION, ChangeKind.OPEN_QUESTION]
    assert evaluation.changes[0].item.status == EpistemicStatus.UNVERIFIED
    assert evaluation.changes[1].question.id == "validate-ai-1"


def test_evaluate_does_not_promote_repetition_that_contradicts(reasoning):
    seeded = state(
        item("k1", "El ciclo itera", EpistemicStatus.ACCEPTED, 0),
        item("ai-1", "El ciclo no itera"),
        questions=[OpenQuestion(id="validate-ai-1", text="¿?", resolved=True)],
    )

    evaluation = reasoning.evaluate(seeded, AIResult(content="El ciclo no itera"), 3)

    assert evaluation.verdict == Verdict.NEEDS_VALIDATION
    assert evaluation.changes == []


def test_double_negation_is_not_a_contradiction(reasoning):
    seeded = state(item("k1", "El ciclo itera", EpistemicStatus.ACCEPTED, 0))

    evaluation = reasoning.evaluate(seeded, AIResult(content="El ciclo no no itera"), 1)

    assert evaluation.verdict == Verdict.ACCEPT


def test_evaluate_rejects_blank_result(reasoning):
    seeded = state(questions=[OpenQuestion(id="q1", text="¿?")])

    evaluation = reasoning.evaluate(seeded, AIResult(content="  \n"), 1)

    assert evaluation.verdict == Verdict.REJECT
    assert evaluation.changes == []


def test_evaluate_closes_the_question_that_was_asked(reasoning):
    seeded = state(
        questions=[OpenQuestion(id="q1", text="¿a?"), OpenQuestion(id="q2", text="¿b?")]
    )

    evaluation = reasoning.evaluate(seeded, AIResult(content="respuesta"), 1)

    assert evaluation.changes[0] == StateChange(
        kind=ChangeKind.CLOSE_QUESTION, target_id="q1"
    )


def test_evaluate_requires_a_cycle_iteration(reasoning):
    with pytest.raises(ValueError):
        reasoning.evaluate(EMPTY, AIResult(content="dato"), 0)


# should_continue


def test_should_continue_while_below_max_iterations(reasoning):
    assert reasoning.should_continue(EMPTY, [trace()] * 2) == (True, None)


def test_should_stop_at_max_iterations(reasoning):
    assert reasoning.should_continue(EMPTY, [trace()] * 3) == (
        False,
        FinishReason.MAX_ITERATIONS,
    )


def test_should_stop_when_purpose_fulfilled(reasoning):
    fulfilled = state(item("ai-1", "dato", EpistemicStatus.ACCEPTED))

    assert reasoning.should_continue(fulfilled, [trace()]) == (
        False,
        FinishReason.PURPOSE_FULFILLED,
    )


def test_purpose_fulfilled_wins_over_max_iterations(reasoning):
    fulfilled = state(item("ai-1", "dato", EpistemicStatus.ACCEPTED))

    assert reasoning.should_continue(fulfilled, [trace()] * 3)[1] == (
        FinishReason.PURPOSE_FULFILLED
    )


def test_open_questions_block_fulfillment(reasoning):
    pending = state(
        item("ai-1", "dato", EpistemicStatus.ACCEPTED),
        questions=[OpenQuestion(id="q1", text="¿?")],
    )

    assert reasoning.should_continue(pending, []) == (True, None)


def test_prior_knowledge_does_not_fulfill_purpose(reasoning):
    seeded = state(item("k1", "dato", EpistemicStatus.ACCEPTED, iteration=0))

    assert reasoning.should_continue(seeded, []) == (True, None)


def test_max_iterations_is_required_and_positive():
    with pytest.raises(TypeError):
        ReasoningSystem()
    with pytest.raises(ValueError):
        ReasoningSystem(max_iterations=0)


# Contra el sistema de información real


def run(reasoning, responses: list[str]) -> tuple[InformationState, list, tuple]:
    """Ciclo mínimo a mano: next_step → respuesta → evaluate → apply."""
    info = InMemoryInformationSystem()
    info.create("s1", PURPOSE)
    decisions = []
    for iteration, response in enumerate(responses, start=1):
        current = info.get_state("s1")
        decisions.append(reasoning.next_step(current).action)
        evaluation = reasoning.evaluate(current, AIResult(content=response), iteration)
        info.apply("s1", evaluation)
    final = info.get_state("s1")
    return (
        final,
        decisions,
        reasoning.should_continue(final, [trace()] * len(responses)),
    )


def test_cycle_explores_verifies_and_fulfills_purpose(reasoning):
    final, decisions, verdict = run(reasoning, ["El ciclo itera", "El ciclo itera."])

    assert decisions == [ActionType.EXPLORE, ActionType.VERIFY]
    assert [i.id for i in final.accepted] == ["ai-1"]
    assert verdict == (False, FinishReason.PURPOSE_FULFILLED)


def test_cycle_without_consensus_ends_by_max_iterations(reasoning):
    final, _, verdict = run(reasoning, ["uno", "dos", "tres"])

    assert final.accepted == []
    assert verdict == (False, FinishReason.MAX_ITERATIONS)


def test_contradiction_becomes_question_that_is_answered_and_closed(reasoning):
    info = InMemoryInformationSystem()
    info.create("s1", PURPOSE)
    info.apply(
        "s1", reasoning.evaluate(info.get_state("s1"), AIResult(content="A es B"), 1)
    )
    info.apply(
        "s1", reasoning.evaluate(info.get_state("s1"), AIResult(content="A es B"), 2)
    )

    current = info.get_state("s1")
    info.apply("s1", reasoning.evaluate(current, AIResult(content="A no es B"), 3))
    current = info.get_state("s1")
    assert [q.id for q in current.open_questions] == ["validate-ai-3"]
    assert reasoning.next_step(current).action == ActionType.ANSWER_QUESTION

    info.apply("s1", reasoning.evaluate(current, AIResult(content="A no es B"), 4))
    final = info.get_state("s1")
    assert final.open_questions == []
    assert [i.id for i in final.unverified] == ["ai-3"]


# Determinismo


def test_all_operations_are_deterministic():
    def outputs():
        reasoning = ReasoningSystem(max_iterations=2)
        seeded = state(
            item("k1", "El ciclo itera", EpistemicStatus.ACCEPTED, 0),
            item("ai-1", "dato"),
            questions=[OpenQuestion(id="q1", text="¿?")],
        )
        return (
            reasoning.next_step(seeded),
            reasoning.evaluate(seeded, AIResult(content="El ciclo no itera"), 2),
            reasoning.should_continue(seeded, [trace()]),
        )

    assert outputs() == outputs()
