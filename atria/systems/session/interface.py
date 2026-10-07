"""Interfaz del almacenamiento de sesiones, independiente del almacenamiento (p1 §5).

El estado de información de una sesión lo posee el sistema de información, que es
quien da de alta la sesión (`InformationSystem.create`). Aquí se guarda el ciclo de
vida: `status`, `finish_reason` y `max_iterations`. Id y propósito no cambian.
"""

from abc import ABC, abstractmethod

from atria.domain import Session


class SessionError(Exception):
    """Operación inválida sobre las sesiones. No modifica lo almacenado."""


class SessionStore(ABC):
    @abstractmethod
    def save(self, session: Session) -> None:
        """Guarda el ciclo de vida de una sesión ya creada en el sistema de información.

        Lanza `SessionError` si la sesión no existe o si su propósito o su estado no
        son los actuales, en vez de descartarlos en silencio.
        """

    @abstractmethod
    def get(self, session_id: str) -> Session:
        """Devuelve la sesión con su estado actual. `SessionError` si no existe.

        Una sesión creada y aún no guardada tiene el ciclo de vida por defecto.
        """
