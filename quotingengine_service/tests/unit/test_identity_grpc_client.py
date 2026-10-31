import uuid
from decimal import Decimal

import grpc
import pytest

from src.application.ports.perfil_cliente_gateway import (
    ClienteNoEncontradoError,
    ConsentimientoNoOtorgadoError,
    PerfilNoDisponibleError,
)
from src.infrastructure.gateways.identity_grpc_client import IdentityGrpcClient
from src.infrastructure.grpc_generated import identity_profile_pb2
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker, EstadoCircuito


def _rpc_error(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata(), "x")


class StubFalso:
    def __init__(self, resultado) -> None:
        self.resultado = resultado
        self.llamadas = 0

    async def ObtenerPerfilCliente(self, request, timeout=None):
        self.llamadas += 1
        if isinstance(self.resultado, BaseException):
            raise self.resultado
        return self.resultado


def _cliente(stub, **kwargs) -> IdentityGrpcClient:
    cliente = IdentityGrpcClient(address="localhost:1", timeout=0.1, **kwargs)
    cliente._stub = stub
    return cliente


async def test_perfil_exitoso():
    cliente_id = uuid.uuid4()
    stub = StubFalso(
        identity_profile_pb2.PerfilClienteResponse(
            id=str(cliente_id),
            nombres="Ana",
            fecha_nacimiento="1990-05-01",
            open_finance_disponible=True,
            ingreso_mensual="8500000",
            ahorros_liquidos="25500000",
            dti_pct="28",
            sobregiros_12_meses=0,
            score=820,
        )
    )

    perfil = await _cliente(stub).obtener_perfil(cliente_id)

    assert perfil.cliente_id == cliente_id
    assert perfil.nombres == "Ana"
    assert perfil.fecha_nacimiento.year == 1990
    assert perfil.ingreso_mensual == Decimal("8500000")
    assert perfil.ahorros_liquidos == Decimal("25500000")
    assert perfil.dti_pct == Decimal("28")
    assert perfil.sobregiros_12_meses == 0
    assert perfil.score == 820


async def test_perfil_con_open_finance_degradado_no_expone_senales():
    cliente_id = uuid.uuid4()
    stub = StubFalso(
        identity_profile_pb2.PerfilClienteResponse(
            id=str(cliente_id), open_finance_disponible=False
        )
    )

    perfil = await _cliente(stub).obtener_perfil(cliente_id)

    assert not perfil.open_finance_disponible
    assert perfil.ingreso_mensual is None
    assert perfil.score is None


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        (grpc.StatusCode.NOT_FOUND, ClienteNoEncontradoError),
        (grpc.StatusCode.PERMISSION_DENIED, ConsentimientoNoOtorgadoError),
        (grpc.StatusCode.UNAVAILABLE, PerfilNoDisponibleError),
        (grpc.StatusCode.DEADLINE_EXCEEDED, PerfilNoDisponibleError),
    ],
)
async def test_traduce_errores_grpc(codigo, esperado):
    with pytest.raises(esperado):
        await _cliente(StubFalso(_rpc_error(codigo))).obtener_perfil(uuid.uuid4())


async def test_error_inesperado_se_normaliza():
    with pytest.raises(PerfilNoDisponibleError):
        await _cliente(StubFalso(RuntimeError("boom"))).obtener_perfil(uuid.uuid4())


async def test_circuito_abierto_evita_llamadas():
    stub = StubFalso(_rpc_error(grpc.StatusCode.UNAVAILABLE))
    cliente = _cliente(stub, circuit_breaker=CircuitBreaker(2, 60))
    for _ in range(2):
        with pytest.raises(PerfilNoDisponibleError):
            await cliente.obtener_perfil(uuid.uuid4())

    with pytest.raises(PerfilNoDisponibleError, match="circuito"):
        await cliente.obtener_perfil(uuid.uuid4())

    assert stub.llamadas == 2


async def test_errores_de_negocio_no_abren_el_circuito():
    breaker = CircuitBreaker(1, 60)
    cliente = _cliente(
        StubFalso(_rpc_error(grpc.StatusCode.NOT_FOUND)), circuit_breaker=breaker
    )
    for _ in range(3):
        with pytest.raises(ClienteNoEncontradoError):
            await cliente.obtener_perfil(uuid.uuid4())

    assert breaker.estado == EstadoCircuito.CERRADO


async def test_bulkhead_saturado_rechaza_rapido():
    cliente = _cliente(StubFalso(None), max_concurrency=1)
    await cliente._bulkhead.acquire()

    with pytest.raises(PerfilNoDisponibleError, match="bulkhead"):
        await cliente.obtener_perfil(uuid.uuid4())
