import uuid
from abc import ABC, abstractmethod

from src.domain.certificados.entities import GeneracionCertificado


class GeneracionEnCursoDuplicadaError(Exception):
    """Ya hay otra generación EN_PROCESO para la póliza."""


class AlmacenamientoCertificadoError(Exception):
    pass


class CertificadoNoEncontradoError(AlmacenamientoCertificadoError):
    """El archivo del certificado no existe en el almacenamiento."""


class GeneracionCertificadoRepository(ABC):
    @abstractmethod
    async def crear(self, generacion: GeneracionCertificado) -> None:
        """Inserta la generación; lanza GeneracionEnCursoDuplicadaError si ya hay una EN_PROCESO."""
        raise NotImplementedError

    @abstractmethod
    async def actualizar(self, generacion: GeneracionCertificado) -> bool:
        """Guarda el resultado solo si sigue EN_PROCESO; False si otro proceso ya la cerró."""
        raise NotImplementedError

    @abstractmethod
    async def obtener_en_proceso(self, poliza_id: uuid.UUID) -> GeneracionCertificado | None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_ultima(self, poliza_id: uuid.UUID) -> GeneracionCertificado | None:
        raise NotImplementedError


class AlmacenamientoCertificadoRepository(ABC):
    @abstractmethod
    async def guardar(self, ruta: str, contenido: bytes) -> None:
        """Guarda el PDF en la ruta relativa dada; si ya existe lo reemplaza."""
        raise NotImplementedError

    @abstractmethod
    async def leer(self, ruta: str) -> bytes:
        """Lee el PDF; lanza CertificadoNoEncontradoError si no existe."""
        raise NotImplementedError

    @abstractmethod
    async def eliminar(self, ruta: str) -> None:
        """Compensación best-effort: no lanza excepción si no se pudo borrar."""
        raise NotImplementedError
