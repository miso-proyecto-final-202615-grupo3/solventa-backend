from abc import ABC, abstractmethod

from src.domain.socios.entities import EventoSocio, Socio


class SocioRepository(ABC):
    @abstractmethod
    async def existe_por_correo(self, correo: str) -> bool: ...

    @abstractmethod
    async def registrar(self, socio: Socio, evento: EventoSocio) -> None: ...

    @abstractmethod
    async def listar(self) -> list[Socio]: ...
