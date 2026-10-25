from abc import ABC, abstractmethod
from typing import Any

from src.domain.open_data import CategoriaOpenData, PerfilTerritorial


class OpenDataNoDisponibleError(Exception):
    pass


class OpenDataGateway(ABC):
    @abstractmethod
    async def obtener_riesgo(self, ubicacion: dict[str, Any]) -> PerfilTerritorial:
        raise NotImplementedError


class OpenDataCachePort(ABC):
    @abstractmethod
    async def obtener(self, ubicacion: dict[str, Any]) -> CategoriaOpenData | None:
        raise NotImplementedError

    @abstractmethod
    async def guardar(
        self, ubicacion: dict[str, Any], perfil: PerfilTerritorial
    ) -> None:
        raise NotImplementedError
