import uuid
from contextlib import asynccontextmanager

import grpc
import pytest

from src.application.use_cases.gestionar_consentimiento_use_case import (
    ConsentimientoNoOtorgadoError,
    PerfilClienteNoEncontradoError,
)
from src.application.ports.open_finance import (
    OpenFinanceNoDisponibleError,
    PerfilOpenFinance,
)
from src.presentation.grpc import identity_profile_pb2, identity_profile_pb2_grpc
from src.presentation.grpc.identity_profile_servicer import IdentityProfileServicer


class UseCaseFalso:
    def __init__(self, resultado) -> None:
        self.resultado = resultado

    async def obtener_perfil_cliente(self, cliente_id):
        if isinstance(self.resultado, BaseException):
            raise self.resultado
        return self.resultado


class OpenFinanceFalso:
    def __init__(self, resultado=None):
        self.resultado = resultado or PerfilOpenFinance(
            ingreso_mensual=8500000,
            ahorros_liquidos=25500000,
            dti_pct=28,
            sobregiros_12_meses=0,
            score=820,
        )
        self.llamadas = 0

    async def obtener_perfil(self, cliente_id):
        self.llamadas += 1
        if isinstance(self.resultado, BaseException):
            raise self.resultado
        return self.resultado


@pytest.fixture
async def stub_factory():
    servers = []

    async def crear(resultado, perfil_open_finance=None):
        @asynccontextmanager
        async def factory():
            yield UseCaseFalso(resultado)

        server = grpc.aio.server()
        identity_profile_pb2_grpc.add_IdentityProfileServicer_to_server(
            IdentityProfileServicer(factory, OpenFinanceFalso(perfil_open_finance)),
            server,
        )
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        servers.append((server, channel))
        return identity_profile_pb2_grpc.IdentityProfileStub(channel)

    yield crear
    for server, channel in servers:
        await channel.close()
        await server.stop(None)


async def test_retorna_perfil(stub_factory):
    cliente_id = uuid.uuid4()
    stub = await stub_factory(
        {
            "id": str(cliente_id),
            "nombres": "Ana",
            "fecha_nacimiento": "1990-05-01",
            "estado_kyc": "VALIDADO",
            "fecha_creacion": "ignorado",
        }
    )

    respuesta = await stub.ObtenerPerfilCliente(
        identity_profile_pb2.ObtenerPerfilClienteRequest(cliente_id=str(cliente_id))
    )

    assert respuesta.id == str(cliente_id)
    assert respuesta.nombres == "Ana"
    assert respuesta.fecha_nacimiento == "1990-05-01"
    assert respuesta.estado_kyc == "VALIDADO"
    assert respuesta.open_finance_disponible
    assert respuesta.ingreso_mensual == "8500000"
    assert respuesta.score == 820


async def test_open_finance_no_disponible_no_impide_consultar_perfil(stub_factory):
    cliente_id = uuid.uuid4()
    stub = await stub_factory(
        {"id": str(cliente_id)}, OpenFinanceNoDisponibleError()
    )

    respuesta = await stub.ObtenerPerfilCliente(
        identity_profile_pb2.ObtenerPerfilClienteRequest(cliente_id=str(cliente_id))
    )

    assert respuesta.id == str(cliente_id)
    assert not respuesta.open_finance_disponible


@pytest.mark.parametrize(
    ("error", "codigo"),
    [
        (ConsentimientoNoOtorgadoError(), grpc.StatusCode.PERMISSION_DENIED),
        (PerfilClienteNoEncontradoError(), grpc.StatusCode.NOT_FOUND),
    ],
)
async def test_traduce_errores_de_negocio(stub_factory, error, codigo):
    stub = await stub_factory(error)

    with pytest.raises(grpc.aio.AioRpcError) as exc:
        await stub.ObtenerPerfilCliente(
            identity_profile_pb2.ObtenerPerfilClienteRequest(
                cliente_id=str(uuid.uuid4())
            )
        )

    assert exc.value.code() == codigo


async def test_cliente_id_invalido(stub_factory):
    stub = await stub_factory({})

    with pytest.raises(grpc.aio.AioRpcError) as exc:
        await stub.ObtenerPerfilCliente(
            identity_profile_pb2.ObtenerPerfilClienteRequest(cliente_id="x")
        )

    assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
