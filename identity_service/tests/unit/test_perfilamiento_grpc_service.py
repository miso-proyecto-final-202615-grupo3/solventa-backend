import uuid
from decimal import Decimal

import grpc
import pytest

from src.application.use_cases.obtener_perfil_financiero_use_case import (
    ClientePerfilNoEncontradoError,
    ConsentimientoNoActivoError,
)
from src.domain.perfilamiento.entities import PerfilOpenFinance
from src.infrastructure.gateways.open_finance_http_client import (
    OpenFinanceUnavailableError,
)
from src.infrastructure.grpc import perfilamiento_pb2
from src.infrastructure.grpc.perfilamiento_server import (
    PerfilamientoGrpcService,
)


class FakeContext:
    def __init__(self):
        self.code = None
        self.details = None

    async def abort(self, code, details):
        self.code = code
        self.details = details
        raise RuntimeError("grpc-abort")


async def test_grpc_retorna_perfil_financiero():
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

    service = PerfilamientoGrpcService(obtener_perfil)
    response = await service.ObtenerPerfilFinanciero(
        perfilamiento_pb2.SolicitudPerfilFinanciero(
            cliente_id=str(cliente_id)
        ),
        FakeContext(),
    )

    assert response.ingreso_mensual == "8500000"
    assert response.proveedor_disponible is True
    assert response.ahorros_liquidos == "25500000"
    assert response.dti_pct == "28"
    assert response.sobregiros_12_meses == 0
    assert response.score == 820


@pytest.mark.parametrize(
    ("error", "codigo"),
    [
        (ClientePerfilNoEncontradoError(), grpc.StatusCode.NOT_FOUND),
        (ConsentimientoNoActivoError(), grpc.StatusCode.PERMISSION_DENIED),
    ],
)
async def test_grpc_mapea_errores_de_perfilamiento(error, codigo):
    async def obtener_perfil(_cliente_id):
        raise error

    context = FakeContext()
    service = PerfilamientoGrpcService(obtener_perfil)

    with pytest.raises(RuntimeError, match="grpc-abort"):
        await service.ObtenerPerfilFinanciero(
            perfilamiento_pb2.SolicitudPerfilFinanciero(
                cliente_id=str(uuid.uuid4())
            ),
            context,
        )

    assert context.code == codigo
    assert context.details


async def test_grpc_rechaza_identificador_invalido():
    context = FakeContext()
    service = PerfilamientoGrpcService(lambda _cliente_id: None)

    with pytest.raises(RuntimeError, match="grpc-abort"):
        await service.ObtenerPerfilFinanciero(
            perfilamiento_pb2.SolicitudPerfilFinanciero(cliente_id="no-uuid"),
            context,
        )

    assert context.code == grpc.StatusCode.INVALID_ARGUMENT


async def test_grpc_distingue_falla_de_proveedor_de_falta_de_consentimiento():
    async def obtener_perfil(_cliente_id):
        raise OpenFinanceUnavailableError()

    service = PerfilamientoGrpcService(obtener_perfil)
    response = await service.ObtenerPerfilFinanciero(
        perfilamiento_pb2.SolicitudPerfilFinanciero(
            cliente_id=str(uuid.uuid4())
        ),
        FakeContext(),
    )

    assert response.proveedor_disponible is False
