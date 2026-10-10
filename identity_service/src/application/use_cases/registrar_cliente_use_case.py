import logging

from src.application.ports.identity_provider import IdentityProvider
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.clientes.value_objects import EstadoKYC
from src.presentation.schemas import ClienteCreate

logger = logging.getLogger(__name__)


class DuplicateClienteError(Exception):
    def __init__(self, detalle: str) -> None:
        self.detalle = detalle
        super().__init__(detalle)


class IdentityProviderError(Exception):
    pass


class RegistrarClienteUseCase:
    def __init__(
        self,
        repository: ClienteRepository,
        identity_provider: IdentityProvider,
    ) -> None:
        self.repository = repository
        self.identity_provider = identity_provider

    async def ejecutar(self, command: ClienteCreate) -> Cliente:
        if await self.repository.existe_por_correo(command.correo):
            raise DuplicateClienteError("Ya existe un cliente con ese correo.")

        if await self.repository.existe_por_documento(
            command.tipo_documento.value, command.numero_identificacion
        ):
            raise DuplicateClienteError(
                "Ya existe un cliente con ese tipo y número de documento."
            )

        cliente = Cliente(
            id=ClienteId(),
            nombres=command.nombres,
            apellidos=command.apellidos,
            tipo_documento=command.tipo_documento.value,
            numero_identificacion=command.numero_identificacion,
            correo=str(command.correo),
            fecha_nacimiento=command.fecha_nacimiento,
            pais_residencia=command.pais_residencia,
            telefono=command.telefono,
            estado_kyc=EstadoKYC.PENDIENTE,
        )

        try:
            await self.identity_provider.registrar_usuario(
                str(command.correo), command.password
            )
        except IdentityProviderError:
            raise
        except Exception as exc:
            logger.exception("No se pudo crear la identidad del cliente")
            raise IdentityProviderError(
                "No se pudo crear la identidad del cliente."
            ) from exc

        try:
            await self.repository.guardar(cliente)
        except Exception:
            logger.exception(
                "Persistencia falló; revirtiendo la identidad creada."
            )
            await self.identity_provider.eliminar_usuario(str(command.correo))
            raise

        return cliente