import uuid
from decimal import Decimal

import grpc
import pytest

from src.domain.perfilamiento.entities import PerfilOpenFinance
from src.infrastructure.grpc import perfilamiento_pb2, perfilamiento_pb2_grpc
from src.infrastructure.grpc.perfilamiento_server import (
    PerfilamientoGrpcService,
)


@pytest.mark.asyncio
async def test_perfilamiento_grpc_serializa_perfil_financiero():
    cliente_id = uuid.uuid4()

    async def obtener_perfil(recibido):
        assert recibido == cliente_id
        return PerfilOpenFinance(
            ingreso_mensual=Decimal("8500000"),
            ahorros_liquidos=Decimal("25500000"),
            dti_pct=Decimal("28"),
            sobregiros_12_meses=0,
            score=820,
        )

    server = grpc.aio.server()
    perfilamiento_pb2_grpc.add_PerfilamientoServicer_to_server(
        PerfilamientoGrpcService(obtener_perfil), server
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = perfilamiento_pb2_grpc.PerfilamientoStub(channel)
            response = await stub.ObtenerPerfilFinanciero(
                perfilamiento_pb2.SolicitudPerfilFinanciero(
                    cliente_id=str(cliente_id)
                ),
                timeout=0.5,
            )
    finally:
        await server.stop(grace=0)

    assert response.ingreso_mensual == "8500000"
    assert response.proveedor_disponible is True
    assert response.ahorros_liquidos == "25500000"
    assert response.dti_pct == "28"
    assert response.sobregiros_12_meses == 0
    assert response.score == 820
