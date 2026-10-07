from itertools import pairwise

import pytest

from atria.domain import (
    CycleStatus,
    FinishReason,
    InformationState,
    Purpose,
    Session,
    build_retrospective,
)
from atria.infrastructure.ai_providers.fake import FakeProvider
from atria.orchestration import Orchestrator
from atria.systems.ai import AIProviderError, AISystem, AITimeoutError
from atria.systems.information import InMemoryInformationSystem
from atria.systems.reasoning import ReasoningSystem
from atria.systems.trace import InMemoryTraceRecorder

PURPOSE = Purpose(text="Entender el ciclo de Atria")
INITIAL = InformationState(purpose=PURPOSE)


class Cycle:
    """El ciclo real con implementaciones en memoria y un provider guionizado."""

    def __init__(
        self,
        script: list[str | AIProviderError],
        max_iterations: int = 5,
        promote_on_repetition: bool = True,
    ) -> None:
        self.provider = FakeProvider(script)
        self.information = InMemoryInformationSystem()
        self.trace = InMemoryTraceRecorder()
        self.orchestrator = Orchestrator(
            self.information,
            ReasoningSystem(max_iterations, promote_on_repetition),
            AISystem(self.provider),
            self.trace,
        )

    def run(self) -> Session:
        state = self.information.create("s1", PURPOSE)
        session, self.retrospective = self.orchestrator.run(
            Session(id="s1", purpose=PURPOSE, state=state)
        )
        return session


def test_cycle_fulfills_purpose_after_several_iterations():
    cycle = Cycle(["El ciclo tiene siete pasos", "El ciclo tiene siete pasos"])

    session = cycle.run()

    assert session.status == CycleStatus.FINISHED
    assert session.finish_reason == FinishReason.PURPOSE_FULFILLED
    assert len(cycle.trace.list("s1")) == 2
    assert [i.content for i in session.state.accepted] == ["El ciclo tiene siete pasos"]


def test_cycle_stops_at_max_iterations_when_purpose_never_fulfilled():
    cycle = Cycle(["uno", "dos", "tres", "cuatro"], max_iterations=3)

    session = cycle.run()

    assert session.finish_reason == FinishReason.MAX_ITERATIONS
    assert len(cycle.provider.requests) == 3
    assert len(cycle.trace.list("s1")) == 3


@pytest.mark.parametrize(
    ("script", "promote", "reason"),
    [
        (["A", "A"], True, FinishReason.PURPOSE_FULFILLED),
        (["uno", "dos", "tres"], False, FinishReason.MAX_ITERATIONS),
    ],
)
def test_traces_chain_states_and_match_final_state(script, promote, reason):
    cycle = Cycle(script, max_iterations=3, promote_on_repetition=promote)

    session = cycle.run()
    traces = cycle.trace.list("s1")

    assert session.finish_reason == reason

    assert [t.iteration for t in traces] == list(range(1, len(traces) + 1))
    assert traces[0].previous_state == INITIAL
    for previous, current in pairwise(traces):
        assert current.previous_state == previous.resulting_state
    assert cycle.information.get_state("s1") == traces[-1].resulting_state
    assert session.state == traces[-1].resulting_state
    assert [t.ai_request for t in traces] == cycle.provider.requests


@pytest.mark.parametrize("k", [1, 2, 3])
@pytest.mark.parametrize("error", [AIProviderError("caído"), AITimeoutError("lento")])
def test_provider_failure_at_iteration_k_ends_with_error(k, error):
    script = ["uno", "dos", "tres"][: k - 1] + [error]
    cycle = Cycle(script, max_iterations=5)

    session = cycle.run()
    traces = cycle.trace.list("s1")

    assert session.finish_reason == FinishReason.ERROR
    assert len(traces) == k - 1
    expected = traces[-1].resulting_state if traces else INITIAL
    assert cycle.information.get_state("s1") == expected
    assert session.state == expected


def test_finished_session_cannot_run_again():
    cycle = Cycle(["A", "A"])
    session = cycle.run()

    with pytest.raises(ValueError, match="ya terminó"):
        cycle.orchestrator.run(session)


@pytest.mark.parametrize(
    ("script", "promote", "reason"),
    [
        (["A", "A"], True, FinishReason.PURPOSE_FULFILLED),
        (["uno", "dos", "tres"], False, FinishReason.MAX_ITERATIONS),
        (["uno", AIProviderError("caído")], True, FinishReason.ERROR),
        ([AIProviderError("caído")], True, FinishReason.ERROR),
    ],
)
def test_cycle_returns_retrospective_of_final_state_and_traces(script, promote, reason):
    cycle = Cycle(script, max_iterations=3, promote_on_repetition=promote)

    session = cycle.run()
    retrospective = cycle.retrospective
    traces = cycle.trace.list("s1")
    final = cycle.information.get_state("s1")

    assert retrospective.finish_reason == session.finish_reason == reason
    assert retrospective.iterations == len(traces)
    assert retrospective.purpose == PURPOSE
    assert retrospective.accepted_knowledge == final.accepted
    assert retrospective.unverified == final.unverified
    assert retrospective.open_questions == final.open_questions
    assert [
        (s.iteration, s.decision, s.applied_changes) for s in retrospective.summary
    ] == [(t.iteration, t.decision, t.applied_changes) for t in traces]
    assert build_retrospective(session, traces) == retrospective
