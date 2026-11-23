"""Tokens push de los dispositivos vinculados (HU4.2.2). El token es un dato sensible: nunca se registra completo."""
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class DestinoPush:
    installation_id: uuid.UUID
    token: str
    plataforma: str


class TokensPushRepository(Protocol):
    async def asignar_a_dispositivo_activo(
        self, cliente_id: uuid.UUID, installation_id: uuid.UUID, token: str, plataforma: str, ahora: datetime
    ) -> bool:
        """Guarda el token en el dispositivo `ACTIVO` del cliente y lo quita de cualquier otro registro.

        Devuelve `False` si esa instalación no está vinculada (activa) al cliente.
        """
        ...

    async def quitar_de_dispositivo(self, cliente_id: uuid.UUID, installation_id: uuid.UUID) -> None: ...

    async def quitar_token(self, token: str) -> None: ...

    async def destinos_de_cliente(self, cliente_id: uuid.UUID) -> list[DestinoPush]: ...
