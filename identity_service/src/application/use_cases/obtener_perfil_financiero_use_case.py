import uuid

from src.application.ports.open_finance import OpenFinanceProvider
from src.domain.clientes.entities import ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.consentimiento.entities import EstadoConsentimiento
from src.domain.consentimiento.repositories import ConsentimientoRepository
from src.domain.perfilamiento.entities import PerfilOpenFinance


class ClientePerfilNoEncontradoError(Exception):
    pass


class ConsentimientoNoActivoError(Exception):
    pass


class ObtenerPerfilFinancieroUseCase:
    def __init__(
        self,
        cliente_repository: ClienteRepository,
        consentimiento_repository: ConsentimientoRepository,
        open_finance_provider: OpenFinanceProvider,
    ) -> None:
        self.cliente_repository = cliente_repository
        self.consentimiento_repository = consentimiento_repository
        self.open_finance_provider = open_finance_provider

    async def ejecutar(self, cliente_id: uuid.UUID) -> PerfilOpenFinance:
        cliente = await self.cliente_repository.obtener_por_id(
            ClienteId(value=cliente_id)
        )
        if cliente is None:
            raise ClientePerfilNoEncontradoError

        consentimiento = await self.consentimiento_repository.obtener_actual(
            cliente_id
        )
        if (
            consentimiento is None
            or consentimiento.estado != EstadoConsentimiento.ACEPTADO
        ):
            raise ConsentimientoNoActivoError

        return await self.open_finance_provider.obtener_perfil_financiero(
            cliente_id
        )
