import uuid
from abc import ABC, abstractmethod

from src.domain.polizas.entities import ContratoPoliza, EstadoCertificado, Poliza


class PolizaDuplicadaError(Exception):
    """Ya existe una póliza con ese número o para esa cotización."""


class PolizaRepository(ABC):
    @abstractmethod
    async def guardar(self, poliza: Poliza) -> Poliza:
        """Persiste la póliza junto con sus coberturas; lanza PolizaDuplicadaError si ya existe."""
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, poliza_id: uuid.UUID) -> Poliza | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_numero(self, numero: str) -> Poliza | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_cotizacion(self, cotizacion_id: uuid.UUID) -> Poliza | None:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_cliente(self, cliente_id: uuid.UUID) -> list[Poliza]:
        raise NotImplementedError

    @abstractmethod
    async def guardar_contrato(self, contrato: ContratoPoliza) -> None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_contrato(self, poliza_id: uuid.UUID) -> ContratoPoliza | None:
        raise NotImplementedError

    @abstractmethod
    async def actualizar_certificado(
        self, poliza_id: uuid.UUID, estado: EstadoCertificado, ruta: str | None
    ) -> None:
        """Registra el estado del certificado y su ruta relativa; no confirma la transacción."""
        raise NotImplementedError
