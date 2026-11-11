import uuid
from abc import ABC, abstractmethod

from src.domain.firmas.entities import ArchivoFirma, FirmaDigital


class FirmaDuplicadaError(Exception):
    """Violación de unicidad: misma clave de idempotencia o firma activa concurrente."""


class AlmacenamientoFirmaError(Exception):
    pass


class FirmaDigitalRepository(ABC):
    @abstractmethod
    async def crear(self, firma: FirmaDigital) -> None:
        """Inserta la firma; lanza FirmaDuplicadaError si viola una restricción de unicidad."""
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_idempotency_key(
        self, cliente_id: uuid.UUID, idempotency_key: str
    ) -> FirmaDigital | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_activa_por_cotizacion(
        self, cotizacion_id: uuid.UUID
    ) -> FirmaDigital | None:
        """Firma vigente (CAPTURADA o VINCULADA) de la cotización."""
        raise NotImplementedError

    @abstractmethod
    async def reemplazar_capturada(self, cotizacion_id: uuid.UUID) -> None:
        """Pasa a REEMPLAZADA la firma CAPTURADA de la cotización, si existe."""
        raise NotImplementedError


class AlmacenamientoFirmaRepository(ABC):
    @abstractmethod
    async def guardar(self, ruta: str, archivo: ArchivoFirma) -> None:
        """Guarda la imagen en la ruta relativa dada (firma-digital/{cliente}/{firma}/...)."""
        raise NotImplementedError

    @abstractmethod
    async def eliminar(self, ruta: str) -> None:
        """Compensación best-effort: no lanza excepción si no se pudo borrar."""
        raise NotImplementedError
