import logging
import uuid

import pytest
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient

from src.core.correlation import CorrelationIdMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware, service="payments_service")

    @app.get("/eco")
    async def eco(x_correlation_id: str | None = Header(default=None)):
        return {"visto": x_correlation_id}

    @app.get("/api/health")
    @app.get("/api/ready")
    async def health():
        return {}

    return app


@pytest.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        yield client


async def test_propaga_el_id_recibido_y_lo_registra(http, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    response = await http.get("/eco?dato=sensible", headers={"X-Correlation-Id": "e2e-123"})

    assert response.json() == {"visto": "e2e-123"}
    assert response.headers["x-correlation-id"] == "e2e-123"
    assert "correlation_id=e2e-123" in caplog.text
    assert "status=200" in caplog.text
    assert "dato=sensible" not in caplog.text


async def test_genera_un_id_si_no_llega_y_lo_ve_el_router(http):
    response = await http.get("/eco")

    generated = response.headers["x-correlation-id"]
    assert response.json() == {"visto": generated}
    assert str(uuid.UUID(generated, version=4)) == generated


@pytest.mark.parametrize("invalid_id", ["x\nFAKE status=200", "x" * 101, ""])
async def test_reemplaza_ids_invalidos(http, caplog, invalid_id):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    response = await http.get("/eco", headers={"X-Correlation-Id": invalid_id})

    generated = response.headers["x-correlation-id"]
    assert response.json() == {"visto": generated}
    assert str(uuid.UUID(generated, version=4)) == generated
    assert "FAKE" not in caplog.text


@pytest.mark.parametrize("path", ["/api/health", "/api/ready"])
async def test_no_registra_health_ni_ready(http, caplog, path):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    response = await http.get(path)

    assert response.status_code == 200
    assert "payments_service_request" not in caplog.text
