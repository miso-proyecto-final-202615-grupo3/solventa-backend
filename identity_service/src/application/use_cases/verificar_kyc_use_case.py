import logging
import uuid

from src.application.ports.kyc import KycVerifier
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.repositories import ClienteRepository

logger = logging.getLogger(__name__)


class KycClienteNoEncontradoError(Exception):
    pass


class VerificarKycUseCase:
    def __init__(
        self,
        repository: ClienteRepository,
        kyc_verifier: KycVerifier,
    ) -> None:
        self.repository = repository
        self.kyc_verifier = kyc_verifier

    async def ejecutar(self, cliente_id: uuid.UUID) -> Cliente:
        cliente = await self.repository.obtener_por_id(ClienteId(value=cliente_id))
        if cliente is None:
            raise KycClienteNoEncontradoError(
                "El cliente indicado no existe."
            )

        estado_kyc = await self.kyc_verifier.verificar(
            cliente.tipo_documento, cliente.numero_identificacion
        )
        await self.repository.actualizar_estado_kyc(cliente.id, estado_kyc)

        cliente.estado_kyc = estado_kyc
        return cliente