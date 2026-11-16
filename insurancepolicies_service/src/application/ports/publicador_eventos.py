from abc import ABC, abstractmethod
from typing import Any


class PublicacionEventoError(Exception):
    pass


class PublicadorEventos(ABC):
    @abstractmethod
    async def publicar(self, tipo: str, payload: dict[str, Any]) -> None:
        """Publica el mensaje en el bus; lanza PublicacionEventoError si no se pudo."""
        raise NotImplementedError
