import asyncio
import uuid

import grpc
import pytest

from src.application.ports.perfil_cliente_gateway import (
    ClienteNoEncontradoError,
    ConsentimientoNoOtorgadoError,
    PerfilNoDisponibleError,
)
from src.infrastructure.gateways.identity_grpc_client import IdentityGrpcClient
from src.infrastructure.grpc_generated import (
    identity_profile_pb2,
    identity_profile_pb2_grpc,
)

CLIENTE_OK = uuid.uuid4()
CLIENTE_SIN_CONSENTIMIENTO = uuid.uuid4()
CLIENTE_LENTO = uuid.uuid4()


class IdentidadFalsa(identity_profile_pb2_grpc.IdentityProfileServicer):
    async def ObtenerPerfilCliente(self, request, context):
        cliente_id = uuid.UUID(request.cliente_id)
        if cliente_id == CLIENTE_OK:
            return identity_profile_pb2.PerfilClienteResponse(
                id=request.cliente_id, nombres="Ana", fecha_nacimiento="1990-05-01"
            )
        if cliente_id == CLIENTE_SIN_CONSENTIMIENTO:
            await context.abort(grpc.StatusCode.PERMISSION_DENIED, "sin consentimiento")
        if cliente_id == CLIENTE_LENTO:
            await asyncio.sleep(1)
        await context.abort(grpc.StatusCode.NOT_FOUND, "no existe")


@pytest.fixture
async def gateway():
    server = grpc.aio.server()
    identity_profile_pb2_grpc.add_IdentityProfileServicer_to_server(
        IdentidadFalsa(), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    client = IdentityGrpcClient(address=f"127.0.0.1:{port}", timeout=0.3)
    yield client
    await client.cerrar()
    await server.stop(None)


async def test_obtiene_perfil_por_grpc(gateway: IdentityGrpcClient):
    perfil = await gateway.obtener_perfil(CLIENTE_OK)

    assert perfil.cliente_id == CLIENTE_OK
    assert perfil.nombres == "Ana"


async def test_errores_de_negocio(gateway: IdentityGrpcClient):
    with pytest.raises(ConsentimientoNoOtorgadoError):
        await gateway.obtener_perfil(CLIENTE_SIN_CONSENTIMIENTO)
    with pytest.raises(ClienteNoEncontradoError):
        await gateway.obtener_perfil(uuid.uuid4())


async def test_timeout_degrada(gateway: IdentityGrpcClient):
    gateway.timeout = 0.05

    with pytest.raises(PerfilNoDisponibleError):
        await gateway.obtener_perfil(CLIENTE_LENTO)


async def test_servicio_caido_degrada():
    client = IdentityGrpcClient(address="127.0.0.1:1", timeout=0.2)
    try:
        with pytest.raises(PerfilNoDisponibleError):
            await client.obtener_perfil(CLIENTE_OK)
    finally:
        await client.cerrar()
