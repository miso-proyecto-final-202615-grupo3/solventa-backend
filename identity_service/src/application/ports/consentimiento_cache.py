from dataclasses import dataclass
from typing import Any, Protocol
import uuid

from src.domain.consentimiento.entities import EstadoConsentimiento


@dataclass(frozen=True)
class ConsentimientoCacheEntry:
    estado: EstadoConsentimiento
    perfil: dict[str, Any] | None


class ConsentimientoCachePort(Protocol):
    async def obtener(
        self, cliente_id: uuid.UUID
    ) -> ConsentimientoCacheEntry | None:
        ...

    async def guardar(
        self,
        cliente_id: uuid.UUID,
        estado: EstadoConsentimiento,
        perfil: dict[str, Any] | None,
    ) -> None:
        ...

    async def invalidar(self, cliente_id: uuid.UUID) -> None:
        ...