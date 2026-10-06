"""Interfaz del sistema de información, independiente del almacenamiento (p1 §2–§3).

Regla central (t1 §4): la información solo se consolida como conocimiento aceptado
mediante un cambio `PROMOTE` de una `Evaluation`. Ninguna otra ruta crea `ACCEPTED`.
"""

from abc import ABC, abstractmethod

from atria.domain import Evaluation, InformationState, Purpose, StateChange


class InformationError(Exception):
    """Operación inválida sobre el sistema de información. No modifica el estado."""


class InformationSystem(ABC):
    @abstractmethod
    def create(self, session_id: str, purpose: Purpose) -> InformationState:
        """Da de alta una sesión con su propósito y las colecciones vacías."""

    @abstractmethod
    def get_state(self, session_id: str) -> InformationState:
        """Devuelve una copia del estado: mutarla no altera el estado interno."""

    @abstractmethod
    def apply(self, session_id: str, evaluation: Evaluation) -> list[StateChange]:
        """Aplica todos los cambios de la evaluación, en orden, o ninguno.

        Devuelve los cambios efectivamente aplicados. Si alguno es inválido lanza
        `InformationError` y el estado queda como estaba.
        """
