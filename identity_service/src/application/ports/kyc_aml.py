import uuid
from abc import ABC, abstractmethod

from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    InicioProveedor,
    ResultadoProveedor,
    RutasDocumentos,
)


class ProveedorKycAmlError(Exception):
    def __init__(self, codigo: str, detalle: str) -> None:
        self.codigo = codigo
        self.detalle = detalle
        super().__init__(detalle)


class KycAmlProvider(ABC):
    nombre: str

    @abstractmethod
    async def iniciar_verificacion(
        self,
        cliente_id: uuid.UUID,
        verificacion_id: uuid.UUID,
        rutas: RutasDocumentos,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
        correlation_id: str,
    ) -> InicioProveedor:
        raise NotImplementedError

    @abstractmethod
    async def consultar_resultado(
        self, verificacion_externa_id: str, correlation_id: str
    ) -> ResultadoProveedor:
        raise NotImplementedError
