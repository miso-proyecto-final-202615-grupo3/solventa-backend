from typing import Protocol

from src.domain.socios.entities import EventoSocio, Socio


class SocioRepository(Protocol):
    async def existe_por_correo(self, correo: str) -> bool: ...

    async def registrar(self, socio: Socio, evento: EventoSocio) -> None: ...

    async def listar(self) -> list[Socio]: ...
