from abc import ABC, abstractmethod
from typing import Optional

from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.value_objects import EstadoKYC
from src.domain.consentimiento.entities import ConsentimientoInicial


class ClienteRepository(ABC):
    @abstractmethod
    async def existe_por_correo(self, correo: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def existe_por_documento(
        self, tipo_documento: str, numero_identificacion: str
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def guardar(
        self, cliente: Cliente, consentimiento: ConsentimientoInicial
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_id(self, cliente_id: ClienteId) -> Optional[Cliente]:
        raise NotImplementedError

    @abstractmethod
    async def obtener_por_correo(self, correo: str) -> Optional[Cliente]:
        raise NotImplementedError

    @abstractmethod
    async def bloquear_para_actualizar(
        self, cliente_id: ClienteId
    ) -> Optional[Cliente]:
        raise NotImplementedError

    @abstractmethod
    async def actualizar_estado_kyc(
        self, cliente_id: ClienteId, estado_kyc: EstadoKYC
    ) -> None:
        raise NotImplementedError
