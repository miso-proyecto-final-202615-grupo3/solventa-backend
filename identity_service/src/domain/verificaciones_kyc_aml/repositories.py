import uuid
from abc import ABC, abstractmethod

from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    RutasDocumentos,
    VerificacionKycAml,
)


class VerificacionDuplicadaError(Exception):
    """La clave de idempotencia del cliente ya tiene una verificación."""


class AlmacenamientoDocumentosError(Exception):
    pass


class VerificacionKycAmlRepository(ABC):
    """Persistencia transaccional: el caso de uso decide cuándo confirmar."""

    @abstractmethod
    async def crear(self, verificacion: VerificacionKycAml) -> None:
        raise NotImplementedError

    @abstractmethod
    async def obtener(
        self, cliente_id: uuid.UUID, verificacion_id: uuid.UUID
    ) -> VerificacionKycAml | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_idempotency_key(
        self, cliente_id: uuid.UUID, idempotency_key: str
    ) -> VerificacionKycAml | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_ultima_id(self, cliente_id: uuid.UUID) -> uuid.UUID | None:
        raise NotImplementedError

    @abstractmethod
    async def actualizar(self, verificacion: VerificacionKycAml) -> bool:
        """Control optimista: False si otra escritura ya cambió la versión."""
        raise NotImplementedError


class DocumentoVerificacionRepository(ABC):
    """Almacén privado de las fotos del documento; la BD solo guarda referencias."""

    @abstractmethod
    async def guardar(
        self,
        cliente_id: uuid.UUID,
        verificacion_id: uuid.UUID,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
    ) -> RutasDocumentos:
        raise NotImplementedError
