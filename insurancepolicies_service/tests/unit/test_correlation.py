import logging

import pytest
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient

from src.core.correlation import CorrelationIdMiddleware


def _app():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware, service="svc")

    @app.get("/eco")
    async def eco(x_correlation_id: str | None = Header(default=None)):
        return {"visto": x_correlation_id}

    @app.get("/api/health")
    async def health():
        return {}

    return app


@pytest.fixture
async def http():
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://test") as client:
        yield client


async def test_propaga_el_id_recibido_y_lo_registra(http, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    response = await http.get("/eco?correo=ana@example.com", headers={"X-Correlation-Id": "e2e-123"})

    assert response.json() == {"visto": "e2e-123"}
    assert response.headers["x-correlation-id"] == "e2e-123"
    assert "correlation_id=e2e-123" in caplog.text
    assert "status=200" in caplog.text
    assert "ana@example.com" not in caplog.text


async def test_genera_un_id_si_no_llega_y_lo_ve_el_router(http):
    response = await http.get("/eco")

    generated = response.headers["x-correlation-id"]
    assert response.json() == {"visto": generated}
    assert len(generated) == 36


async def test_reemplaza_ids_con_caracteres_peligrosos(http, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    response = await http.get("/eco", headers={"X-Correlation-Id": "x\nFAKE status=200"})

    assert response.json()["visto"] != "x\nFAKE status=200"
    assert "FAKE" not in caplog.text


async def test_no_registra_health(http, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    await http.get("/api/health")

    assert "svc_request" not in caplog.text
