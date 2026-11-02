import json

import httpx
import pytest

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)

BASE = "http://identity-host:8000"
PATH_AUTENTICAR = "/api/v1/identity-service/clientes/autenticar"


async def test_autenticar_cliente_llama_al_ms_identidad():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"access_token": "access-123"})

    gateway = IdentityServiceGateway(base_url=BASE, transport=httpx.MockTransport(handler))
    try:
        resultado = await gateway.autenticar_cliente("ana.perez@example.com", "Secreta123")

        assert resultado["access_token"] == "access-123"
        assert str(calls[0].url) == f"{BASE}{PATH_AUTENTICAR}"
        assert json.loads(calls[0].content) == {
            "correo": "ana.perez@example.com",
            "password": "Secreta123",
        }
    finally:
        await gateway.aclose()


async def test_autenticar_cliente_propaga_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Credenciales inválidas."})

    gateway = IdentityServiceGateway(base_url=BASE, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.autenticar_cliente("ana.perez@example.com", "mala")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Credenciales inválidas."
    finally:
        await gateway.aclose()


async def test_autenticar_cliente_mapea_error_de_red_como_503():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    gateway = IdentityServiceGateway(base_url=BASE, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.autenticar_cliente("ana.perez@example.com", "Secreta123")
        assert exc.value.status_code == 503
    finally:
        await gateway.aclose()


async def test_autenticar_cliente_error_sin_cuerpo_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    gateway = IdentityServiceGateway(base_url=BASE, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(IdentityGatewayError) as exc:
            await gateway.autenticar_cliente("ana.perez@example.com", "Secreta123")
        assert exc.value.status_code == 500
    finally:
        await gateway.aclose()


async def test_inicia_activacion_y_propagacion_de_correlacion():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Correlation-Id"] == "corr-123"
        assert json.loads(request.content) == {
            "correo": "ana@example.com",
            "installation_id": "instalacion-1",
            "plataforma": "ANDROID",
            "modelo": "Pixel",
            "version_so": "15",
        }
        return httpx.Response(
            201,
            json={
                "dispositivo_vinculado": False,
                "sesion_id": "sesion-1",
                "intentos_restantes": 3,
            },
        )

    gateway = IdentityServiceGateway(
        base_url=BASE, transport=httpx.MockTransport(handler)
    )
    try:
        response = await gateway.iniciar_activacion_movil(
            "ana@example.com",
            {
                "installation_id": "instalacion-1",
                "plataforma": "ANDROID",
                "modelo": "Pixel",
                "version_so": "15",
            },
            "corr-123",
        )
    finally:
        await gateway.aclose()

    assert response["sesion_id"] == "sesion-1"
