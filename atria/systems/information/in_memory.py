"""Sistema de información en memoria, para desarrollar y testear el ciclo sin BD.

Transiciones permitidas (provisionales, gap G3):
- `ADD_INFORMATION`: solo items `UNVERIFIED`; la información nueva nunca entra
  como conocimiento ni como contexto por esta vía.
- `PROMOTE`: `UNVERIFIED` → `ACCEPTED`. Es la aceptación explícita del item; no se
  condiciona al `verdict`, que califica el resultado de IA en su conjunto (gap G1).
- `REJECT`: elimina un item `UNVERIFIED`. No hay estado "rechazado" ni revocación de
  conocimiento aceptado (gap G3); la traza de la iteración conserva el item.
- `OPEN_QUESTION` / `CLOSE_QUESTION`: añade una pregunta / resuelve una abierta.
"""

from atria.domain import (
    ChangeKind,
    EpistemicStatus,
    Evaluation,
    InformationItem,
    InformationState,
    OpenQuestion,
    Purpose,
    StateChange,
)
from atria.systems.information.interface import InformationError, InformationSystem


class InMemoryInformationSystem(InformationSystem):
    def __init__(self) -> None:
        self._states: dict[str, InformationState] = {}

    def create(self, session_id: str, purpose: Purpose) -> InformationState:
        if session_id in self._states:
            raise InformationError(f"la sesión '{session_id}' ya existe")
        self._states[session_id] = InformationState(purpose=purpose)
        return self.get_state(session_id)

    def get_state(self, session_id: str) -> InformationState:
        return self._stored(session_id).model_copy(deep=True)

    def apply(self, session_id: str, evaluation: Evaluation) -> list[StateChange]:
        state = self.get_state(session_id)
        applied = [change.model_copy(deep=True) for change in evaluation.changes]
        for change in applied:
            apply_change(state, change)
        self._states[session_id] = state
        return applied

    def _stored(self, session_id: str) -> InformationState:
        try:
            return self._states[session_id]
        except KeyError:
            raise InformationError(f"la sesión '{session_id}' no existe") from None


def apply_change(state: InformationState, change: StateChange) -> None:
    """Aplica un cambio sobre `state` según las transiciones de este módulo.

    Muta `state`; lo comparten todas las implementaciones del sistema de información.
    """
    match change.kind:
        case ChangeKind.ADD_INFORMATION:
            item = change.item
            if item.status != EpistemicStatus.UNVERIFIED:
                raise InformationError(
                    f"la información nueva '{item.id}' debe entrar como unverified"
                )
            if any(existing.id == item.id for existing in state.items):
                raise InformationError(f"el item '{item.id}' ya existe")
            state.items.append(item.model_copy())
        case ChangeKind.PROMOTE:
            _unverified(state, change.target_id).status = EpistemicStatus.ACCEPTED
        case ChangeKind.REJECT:
            state.items.remove(_unverified(state, change.target_id))
        case ChangeKind.OPEN_QUESTION:
            question = change.question
            if any(existing.id == question.id for existing in state.questions):
                raise InformationError(f"la pregunta '{question.id}' ya existe")
            state.questions.append(question.model_copy())
        case ChangeKind.CLOSE_QUESTION:
            _open_question(state, change.target_id).resolved = True


def _unverified(state: InformationState, item_id: str) -> InformationItem:
    for item in state.unverified:
        if item.id == item_id:
            return item
    raise InformationError(f"no hay información no verificada con id '{item_id}'")


def _open_question(state: InformationState, question_id: str) -> OpenQuestion:
    for question in state.open_questions:
        if question.id == question_id:
            return question
    raise InformationError(f"no hay pregunta abierta con id '{question_id}'")
