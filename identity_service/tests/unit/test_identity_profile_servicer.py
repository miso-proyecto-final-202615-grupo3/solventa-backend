import uuid
from contextlib import asynccontextmanager

import grpc
import pytest

from src.application.use_cases.gestionar_consentimiento_use_case import (
    ConsentimientoNoOtorgadoError,
    PerfilClienteNoEncontradoError,
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


@pytest.fixture
async def stub_factory():
    servers = []

    async def crear(resultado):
        @asynccontextmanager
        async def factory():
            yield UseCaseFalso(resultado)

        server = grpc.aio.server()
        identity_profile_pb2_grpc.add_IdentityProfileServicer_to_server(
            IdentityProfileServicer(factory), server
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
