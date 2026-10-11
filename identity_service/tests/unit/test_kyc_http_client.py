import httpx

from src.domain.clientes.value_objects import EstadoKYC
from src.infrastructure.gateways.kyc_http_client import KycHttpClient

BASE = "http://kyc-host:8202"


def _client(handler) -> KycHttpClient:
    return KycHttpClient(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )


def _handler_con_estado(status: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"verification_id": "ver-1", "status": status}
        )

    return handler


async def test_mapea_passed_a_validado():
    client = _client(_handler_con_estado("PASSED"))
    try:
        assert (
            await client.verificar("CC", "1020304050") == EstadoKYC.VALIDADO
        )
    finally:
        await client.aclose()


async def test_mapea_failed_a_rechazado():
    client = _client(_handler_con_estado("FAILED"))
    try:
        assert (
            await client.verificar("CC", "1020304050") == EstadoKYC.RECHAZADO
        )
    finally:
        await client.aclose()


async def test_mapea_pending_a_pendiente():
    client = _client(_handler_con_estado("PENDING"))
    try:
        assert (
            await client.verificar("CC", "1020304050") == EstadoKYC.PENDIENTE
        )
    finally:
        await client.aclose()


async def test_degrada_a_pendiente_si_el_proveedor_falla():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    client = _client(handler)
    try:
        assert (
            await client.verificar("CC", "1020304050") == EstadoKYC.PENDIENTE
        )
    finally:
        await client.aclose()


async def test_degrada_a_pendiente_si_responde_error_http():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "no disponible"})

    client = _client(handler)
    try:
        assert (
            await client.verificar("CC", "1020304050") == EstadoKYC.PENDIENTE
        )
    finally:
        await client.aclose()


async def test_degrada_a_pendiente_si_respuesta_no_es_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="boom")

    client = _client(handler)
    try:
        assert (
            await client.verificar("CC", "1020304050") == EstadoKYC.PENDIENTE
        )
    finally:
        await client.aclose()