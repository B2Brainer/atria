import pytest

from atria.domain import (
    ChangeKind,
    EpistemicStatus,
    Evaluation,
    InformationItem,
    InformationState,
    OpenQuestion,
    Origin,
    Purpose,
    StateChange,
    Verdict,
)
from atria.systems.information import (
    InformationError,
    InformationSystem,
    InMemoryInformationSystem,
)

SESSION = "s1"
PURPOSE = Purpose(text="Entender el ciclo de Atria")


def item(id: str, status: EpistemicStatus = EpistemicStatus.UNVERIFIED):
    return InformationItem(
        id=id, content=f"contenido {id}", status=status, origin=Origin.AI, iteration=1
    )


def add(id: str, status: EpistemicStatus = EpistemicStatus.UNVERIFIED) -> StateChange:
    return StateChange(kind=ChangeKind.ADD_INFORMATION, item=item(id, status))


def targeting(kind: ChangeKind, target_id: str) -> StateChange:
    return StateChange(kind=kind, target_id=target_id)


def open_question(id: str) -> StateChange:
    question = OpenQuestion(id=id, text=f"¿{id}?")
    return StateChange(kind=ChangeKind.OPEN_QUESTION, question=question)


def evaluation(*changes: StateChange) -> Evaluation:
    return Evaluation(verdict=Verdict.ACCEPT, changes=list(changes))


@pytest.fixture
def system() -> InformationSystem:
    system = InMemoryInformationSystem()
    system.create(SESSION, PURPOSE)
    return system


def test_in_memory_implements_interface():
    assert isinstance(InMemoryInformationSystem(), InformationSystem)


def test_new_session_has_purpose_and_empty_collections(system):
    assert system.get_state(SESSION) == InformationState(purpose=PURPOSE)


def test_add_information_enters_as_unverified(system):
    system.apply(SESSION, evaluation(add("i1")))

    state = system.get_state(SESSION)
    assert state.unverified == [item("i1")]
    assert state.accepted == []


def test_promote_moves_item_to_accepted(system):
    system.apply(SESSION, evaluation(add("i1"), add("i2")))

    system.apply(SESSION, evaluation(targeting(ChangeKind.PROMOTE, "i1")))

    state = system.get_state(SESSION)
    assert state.accepted == [item("i1", EpistemicStatus.ACCEPTED)]
    assert state.unverified == [item("i2")]


def test_add_and_promote_in_same_evaluation_apply_in_order(system):
    system.apply(SESSION, evaluation(add("i1"), targeting(ChangeKind.PROMOTE, "i1")))

    assert system.get_state(SESSION).accepted == [item("i1", EpistemicStatus.ACCEPTED)]


def test_reject_removes_unverified_item(system):
    system.apply(SESSION, evaluation(add("i1"), add("i2")))

    system.apply(SESSION, evaluation(targeting(ChangeKind.REJECT, "i1")))

    assert system.get_state(SESSION).items == [item("i2")]


def test_open_and_close_question(system):
    system.apply(SESSION, evaluation(open_question("q1"), open_question("q2")))

    system.apply(SESSION, evaluation(targeting(ChangeKind.CLOSE_QUESTION, "q1")))

    state = system.get_state(SESSION)
    assert [q.id for q in state.open_questions] == ["q2"]
    assert [q.id for q in state.questions] == ["q1", "q2"]


@pytest.mark.parametrize(
    "invalid",
    [
        pytest.param(targeting(ChangeKind.PROMOTE, "nope"), id="promote-missing"),
        pytest.param(targeting(ChangeKind.PROMOTE, "a1"), id="promote-accepted"),
        pytest.param(targeting(ChangeKind.REJECT, "nope"), id="reject-missing"),
        pytest.param(targeting(ChangeKind.REJECT, "a1"), id="reject-accepted"),
        pytest.param(add("x", EpistemicStatus.ACCEPTED), id="add-as-accepted"),
        pytest.param(add("x", EpistemicStatus.CONTEXT), id="add-as-context"),
        pytest.param(add("u1"), id="add-duplicate"),
        pytest.param(open_question("q1"), id="open-duplicate"),
        pytest.param(targeting(ChangeKind.CLOSE_QUESTION, "nope"), id="close-missing"),
        pytest.param(targeting(ChangeKind.CLOSE_QUESTION, "q2"), id="close-closed"),
    ],
)
def test_invalid_change_raises_and_leaves_state_unchanged(system, invalid):
    system.apply(
        SESSION,
        evaluation(
            add("u1"),
            add("a1"),
            targeting(ChangeKind.PROMOTE, "a1"),
            open_question("q1"),
            open_question("q2"),
            targeting(ChangeKind.CLOSE_QUESTION, "q2"),
        ),
    )
    before = system.get_state(SESSION)

    # Un cambio válido previo en la misma evaluación tampoco debe quedar aplicado.
    with pytest.raises(InformationError):
        system.apply(SESSION, evaluation(add("ok"), invalid))

    assert system.get_state(SESSION) == before


def test_get_state_returns_a_copy(system):
    system.apply(SESSION, evaluation(add("i1"), open_question("q1")))

    state = system.get_state(SESSION)
    state.items[0].status = EpistemicStatus.ACCEPTED
    state.items.append(item("i2"))
    state.questions[0].resolved = True

    assert system.get_state(SESSION).items == [item("i1")]
    assert system.get_state(SESSION).open_questions[0].id == "q1"


def test_applied_changes_do_not_alias_internal_state(system):
    change = add("i1")

    applied = system.apply(SESSION, evaluation(change))
    change.item.status = EpistemicStatus.ACCEPTED
    applied[0].item.status = EpistemicStatus.ACCEPTED

    assert system.get_state(SESSION).accepted == []


def test_apply_returns_exactly_the_applied_changes(system):
    changes = [add("i1"), targeting(ChangeKind.PROMOTE, "i1"), open_question("q1")]

    assert system.apply(SESSION, evaluation(*changes)) == changes


def test_apply_with_no_changes_returns_empty_list(system):
    assert system.apply(SESSION, evaluation()) == []
    assert system.get_state(SESSION) == InformationState(purpose=PURPOSE)


def test_sessions_are_isolated(system):
    system.create("s2", Purpose(text="Otro propósito"))

    system.apply(SESSION, evaluation(add("i1")))

    assert system.get_state("s2").items == []


@pytest.mark.parametrize(
    "operation",
    [
        lambda s: s.get_state("nope"),
        lambda s: s.apply("nope", evaluation()),
        lambda s: s.create(SESSION, PURPOSE),
    ],
    ids=["get-unknown", "apply-unknown", "create-duplicate"],
)
def test_session_errors_are_domain_errors(system, operation):
    with pytest.raises(InformationError):
        operation(system)
