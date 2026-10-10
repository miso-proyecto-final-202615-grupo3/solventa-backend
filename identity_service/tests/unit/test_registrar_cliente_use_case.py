import uuid
from datetime import date

import pytest

from src.application.ports.identity_provider import IdentityProvider
from src.application.use_cases.registrar_cliente_use_case import (
    DuplicateClienteError,
    IdentityProviderError,
    RegistrarClienteUseCase,
)
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.clientes.value_objects import EstadoKYC
from src.presentation.schemas import ClienteCreate

PAYLOAD = ClienteCreate(
    nombres="Ana",
    apellidos="Pérez",
    tipo_documento="CC",
    numero_identificacion="1020304050",
    correo="ana.perez@example.com",
    password="Secreta123",
    fecha_nacimiento=date(1990, 5, 15),
    pais_residencia="Colombia",
    telefono="+573001234567",
)


def _cliente(
    correo: str = "ana.perez@example.com",
    numero_identificacion: str = "1020304050",
) -> Cliente:
    return Cliente(
        id=ClienteId(),
        nombres="Ana",
        apellidos="Pérez",
        tipo_documento="CC",
        numero_identificacion=numero_identificacion,
        correo=correo,
        fecha_nacimiento=date(1990, 5, 15),
        pais_residencia="Colombia",
        telefono="+573001234567",
        estado_kyc=EstadoKYC.PENDIENTE,
    )


class InMemoryClienteRepository(ClienteRepository):
    def __init__(self):
        self.clientes: list[Cliente] = []

    async def existe_por_correo(self, correo: str) -> bool:
        return any(c.correo == correo for c in self.clientes)

    async def existe_por_documento(
        self, tipo_documento: str, numero_identificacion: str
    ) -> bool:
        return any(
            c.tipo_documento == tipo_documento
            and c.numero_identificacion == numero_identificacion
            for c in self.clientes
        )

    async def guardar(self, cliente: Cliente) -> None:
        self.clientes.append(cliente)


class FailingClienteRepository(InMemoryClienteRepository):
    async def guardar(self, cliente: Cliente) -> None:
        raise RuntimeError("base de datos no disponible")


async def test_registra_cliente_y_crea_credenciales(fake_identity_provider):
    repo = InMemoryClienteRepository()
    use_case = RegistrarClienteUseCase(repo, fake_identity_provider)

    cliente = await use_case.ejecutar(PAYLOAD)

    assert isinstance(cliente.id.value, uuid.UUID)
    assert cliente.correo == PAYLOAD.correo
    assert cliente.numero_identificacion == PAYLOAD.numero_identificacion
    assert cliente.estado_kyc == EstadoKYC.PENDIENTE
    assert fake_identity_provider.registrados == [
        (PAYLOAD.correo, PAYLOAD.password)
    ]
    assert len(repo.clientes) == 1


async def test_rechaza_correo_duplicado(fake_identity_provider):
    repo = InMemoryClienteRepository()
    await repo.guardar(_cliente(correo=PAYLOAD.correo))
    use_case = RegistrarClienteUseCase(repo, fake_identity_provider)

    with pytest.raises(DuplicateClienteError):
        await use_case.ejecutar(PAYLOAD)

    assert fake_identity_provider.registrados == []


async def test_rechaza_documento_duplicado(fake_identity_provider):
    repo = InMemoryClienteRepository()
    await repo.guardar(_cliente(correo="otro@example.com"))
    use_case = RegistrarClienteUseCase(repo, fake_identity_provider)

    with pytest.raises(DuplicateClienteError):
        await use_case.ejecutar(PAYLOAD)

    assert fake_identity_provider.registrados == []


async def test_elimina_identidad_si_falla_la_persistencia(fake_identity_provider):
    repo = FailingClienteRepository()
    use_case = RegistrarClienteUseCase(repo, fake_identity_provider)

    with pytest.raises(RuntimeError):
        await use_case.ejecutar(PAYLOAD)

    assert fake_identity_provider.eliminados == [PAYLOAD.correo]


class FailingIdentityProvider(IdentityProvider):
    async def registrar_usuario(self, correo: str, password: str) -> None:
        raise IdentityProviderError("cognito falló")

    async def eliminar_usuario(self, correo: str) -> None:
        pass


async def test_propaga_error_de_identidad():
    repo = InMemoryClienteRepository()
    identity_provider = FailingIdentityProvider()
    use_case = RegistrarClienteUseCase(repo, identity_provider)

    with pytest.raises(IdentityProviderError):
        await use_case.ejecutar(PAYLOAD)

    assert repo.clientes == []