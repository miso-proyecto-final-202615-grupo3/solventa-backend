import json

import httpx
import pytest

from tests.conftest import BASE, CLIENTE, COTIZACION, IDENTITY, SOCIO


async def test_key_ausente_no_llama_a_backend(bff):
    client, backend = bff
    response = await client.get(f"{BASE}/productos")
    assert response.status_code == 401
    assert backend.llamadas == []


async def test_key_invalida_propaga_error_de_identidad(bff, headers_cliente):
    client, backend = bff
    backend.responder("POST", f"{IDENTITY}/socios/validar-api-key", httpx.Response(401, json={"detail": "Clave inválida"}))
    response = await client.get(f"{BASE}/productos", headers=headers_cliente)
    assert response.status_code == 401 and response.json() == {"detail": "Clave inválida"}
    assert len(backend.llamadas) == 1
    assert json.loads(backend.llamadas[0].content) == {"api_key": "clave-socio"}


async def test_cliente_sin_asociacion_no_accede_al_backend(bff, headers_cliente):
    client, backend = bff
    ruta = f"{IDENTITY}/socios/{SOCIO}/clientes/{CLIENTE}/autorizacion"
    backend.responder("GET", ruta, httpx.Response(403, json={"detail": "No autorizado"}))
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}", headers=headers_cliente)
    assert response.status_code == 403 and response.json() == {"detail": "No autorizado"}
    assert [(r.method, r.url.path) for r in backend.llamadas] == [
        ("POST", f"{IDENTITY}/socios/validar-api-key"), ("GET", ruta)
    ]


@pytest.mark.parametrize("data", [{}, {"socio_id": "no-es-uuid"}])
async def test_identidad_invalida_no_autoriza(bff, headers_cliente, data):
    client, backend = bff
    backend.responder("POST", f"{IDENTITY}/socios/validar-api-key", httpx.Response(200, json=data))
    response = await client.get(f"{BASE}/productos", headers=headers_cliente)
    assert response.status_code == 502 and len(backend.llamadas) == 1


@pytest.mark.parametrize("value", [None, "no-es-uuid"])
async def test_cliente_header_obligatorio_y_uuid(bff, headers_cliente, value):
    client, backend = bff
    if value is None:
        headers_cliente.pop("X-Client-Id")
    else:
        headers_cliente["X-Client-Id"] = value
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}", headers=headers_cliente)
    assert response.status_code == 422
    assert all(r.url.path == f"{IDENTITY}/socios/validar-api-key" for r in backend.llamadas)


async def test_asociacion_con_respuesta_exitosa_invalida_no_autoriza(bff, headers_cliente):
    client, backend = bff
    ruta = f"{IDENTITY}/socios/{SOCIO}/clientes/{CLIENTE}/autorizacion"
    backend.responder("GET", ruta, httpx.Response(200, json={"autorizado": True}))
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}", headers=headers_cliente)
    assert response.status_code == 502
    assert len(backend.llamadas) == 2
