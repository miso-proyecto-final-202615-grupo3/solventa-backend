import json

import httpx
import pytest

from src.application.ports.liveness import (
    LivenessAdapterUnavailableError,
    LivenessSessionConflictError,
    LivenessSessionNotFoundError,
)
from src.infrastructure.gateways.http_liveness_adapter_client import HttpLivenessAdapterClient


BASE = "http://liveness-host:8203"


def _client(handler) -> HttpLivenessAdapterClient:
    return HttpLivenessAdapterClient(
        base_url=BASE,
        transport=httpx.MockTransport(handler),
    )


async def test_inicia_sesion_y_preserva_el_contexto_de_trazabilidad():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{BASE}/api/v1/liveness-adapter/liveness/sessions"
        assert request.headers["X-Correlation-Id"] == "corr-123"
        assert json.loads(request.content) == {"customer_id": "cliente-456"}
        return httpx.Response(
            201,
            json={
                "session_id": "sesion-789",
                "expires_at": "2026-10-25T12:00:00Z",
                "capture": {"kind": "FRAMES", "nonce": "nonce-seguro"},
            },
        )

    client = _client(handler)
    try:
        session = await client.start_session("cliente-456", "corr-123")
    finally:
        await client.aclose()

    assert session.session_id == "sesion-789"
    assert session.expires_at == "2026-10-25T12:00:00Z"
    assert session.capture == {"kind": "FRAMES", "nonce": "nonce-seguro"}


async def test_traduce_error_http_a_error_del_puerto():
    client = _client(lambda request: httpx.Response(503, json={"detail": "no disponible"}))
    try:
        with pytest.raises(LivenessAdapterUnavailableError):
            await client.start_session("cliente-456", "corr-123")
    finally:
        await client.aclose()


async def test_traduce_respuesta_invalida_a_error_del_puerto():
    client = _client(lambda request: httpx.Response(201, json={"session_id": "sesion-789"}))
    try:
        with pytest.raises(LivenessAdapterUnavailableError):
            await client.start_session("cliente-456", "corr-123")
    finally:
        await client.aclose()


async def test_cancela_sesion_y_propagacion_de_correlacion():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{BASE}/api/v1/liveness-adapter/liveness/sessions/sesion-789/cancel"
        assert request.headers["X-Correlation-Id"] == "corr-123"
        return httpx.Response(204)

    client = _client(handler)
    try:
        await client.cancel_session("sesion-789", "corr-123")
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("status_code", "error"),
    [
        (404, LivenessSessionNotFoundError),
        (409, LivenessSessionConflictError),
        (503, LivenessAdapterUnavailableError),
    ],
)
async def test_mapea_errores_de_cancelacion(status_code, error):
    client = _client(lambda request: httpx.Response(status_code))
    try:
        with pytest.raises(error):
            await client.cancel_session("sesion-789", "corr-123")
    finally:
        await client.aclose()
