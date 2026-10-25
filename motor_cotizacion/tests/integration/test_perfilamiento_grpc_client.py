from decimal import Decimal
import uuid

import grpc
import pytest

from src.application.ports.perfilamiento import (
    ConsentimientoNoActivoError,
    OpenFinanceNoDisponibleError,
    PerfilamientoNoDisponibleError,
)
from src.infrastructure.grpc import perfilamiento_pb2, perfilamiento_pb2_grpc
from src.infrastructure.gateways.perfilamiento_grpc_client import (
    PerfilamientoGrpcClient,
)


class FakePerfilamientoService(
    perfilamiento_pb2_grpc.PerfilamientoServicer
):
    def __init__(self, code=None, provider_available=True):
        self.code = code
        self.provider_available = provider_available

    async def ObtenerPerfilFinanciero(self, request, context):
        if self.code:
            await context.abort(self.code, "fallo simulado")
        return perfilamiento_pb2.RespuestaPerfilFinanciero(
            proveedor_disponible=self.provider_available,
            ingreso_mensual="8500000",
            ahorros_liquidos="25500000",
            dti_pct="28",
            sobregiros_12_meses=0,
            score=820,
        )


async def invocar_cliente(service, cliente_id):
    server = grpc.aio.server()
    perfilamiento_pb2_grpc.add_PerfilamientoServicer_to_server(
        service, server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            client = PerfilamientoGrpcClient(channel, timeout_seconds=0.2)
            return await client.obtener_perfil_financiero(cliente_id)
    finally:
        await server.stop(grace=0)


async def test_cliente_grpc_obtiene_perfil_financiero():
    profile = await invocar_cliente(
        FakePerfilamientoService(), uuid.uuid4()
    )

    assert profile.ingreso_mensual == Decimal("8500000")
    assert profile.ahorros_liquidos == Decimal("25500000")
    assert profile.dti_pct == Decimal("28")
    assert profile.score == 820


async def test_falla_open_finance_se_identifica_como_degradacion():
    with pytest.raises(OpenFinanceNoDisponibleError):
        await invocar_cliente(
            FakePerfilamientoService(provider_available=False), uuid.uuid4()
        )


@pytest.mark.parametrize(
    ("code", "error"),
    [
        (grpc.StatusCode.PERMISSION_DENIED, ConsentimientoNoActivoError),
        (grpc.StatusCode.UNAVAILABLE, PerfilamientoNoDisponibleError),
        (grpc.StatusCode.DEADLINE_EXCEEDED, PerfilamientoNoDisponibleError),
    ],
)
async def test_traduce_estados_grpc(code, error):
    with pytest.raises(error):
        await invocar_cliente(
            FakePerfilamientoService(code=code), uuid.uuid4()
        )
