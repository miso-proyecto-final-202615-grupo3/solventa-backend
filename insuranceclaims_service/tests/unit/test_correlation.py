import logging

import pytest
from fastapi import FastAPI, Header
from httpx import ASGITransport, AsyncClient

from src.core.correlation import CorrelationIdMiddleware


@pytest.fixture
async def http():
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware, service="insuranceclaims_service")

    @app.get("/eco")
    async def eco(x_correlation_id: str | None = Header(default=None)):
        return {"visto": x_correlation_id}

    @app.get("/health")
    async def health():
        return {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_propaga_id_y_no_registra_query(http, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    response = await http.get("/eco?dato=privado", headers={"X-Correlation-Id": "claim-123"})
    assert response.json() == {"visto": "claim-123"}
    assert response.headers["x-correlation-id"] == "claim-123"
    assert "correlation_id=claim-123" in caplog.text
    assert "dato=privado" not in caplog.text


async def test_genera_id_si_no_llega(http):
    response = await http.get("/eco")
    assert response.json()["visto"] == response.headers["x-correlation-id"]
    assert len(response.headers["x-correlation-id"]) == 36


async def test_reemplaza_id_invalido(http, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    response = await http.get("/eco", headers={"X-Correlation-Id": "x\nFAKE status=200"})
    assert response.json()["visto"] != "x\nFAKE status=200"
    assert "FAKE" not in caplog.text


async def test_no_registra_health(http, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    await http.get("/health")
    assert "insuranceclaims_service_request" not in caplog.text
