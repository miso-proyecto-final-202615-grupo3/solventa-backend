from typing import Protocol

from src.domain.socios.entities import EventoSocio, Socio


class SocioRepository(Protocol):
    async def registrar(self, socio: Socio, evento: EventoSocio) -> None: ...
