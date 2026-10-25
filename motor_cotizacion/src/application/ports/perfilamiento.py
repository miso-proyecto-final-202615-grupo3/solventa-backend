from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any
import uuid

from src.domain.open_data import CategoriaOpenData, PerfilTerritorial
from src.domain.pricing import PerfilFinanciero


class ConsentimientoNoActivoError(Exception):
    pass


class ClienteCotizacionNoEncontradoError(Exception):
    pass


class OpenFinanceNoDisponibleError(Exception):
    pass


class PerfilamientoNoDisponibleError(Exception):
    pass


class OpenDataNoDisponibleError(Exception):
    pass


class PerfilFinancieroProvider(ABC):
    @abstractmethod
    async def obtener_perfil_financiero(
        self, cliente_id: uuid.UUID
    ) -> PerfilFinanciero:
        raise NotImplementedError


class OpenDataProvider(ABC):
    @abstractmethod
    async def obtener_riesgo_territorial(
        self, ubicacion: dict[str, Any]
    ) -> PerfilTerritorial:
        raise NotImplementedError


class OpenDataCachePort(ABC):
    @abstractmethod
    async def obtener(
        self, ubicacion: dict[str, Any]
    ) -> CategoriaOpenData | None:
        raise NotImplementedError

    @abstractmethod
    async def guardar(
        self, ubicacion: dict[str, Any], perfil: PerfilTerritorial
    ) -> None:
        raise NotImplementedError
