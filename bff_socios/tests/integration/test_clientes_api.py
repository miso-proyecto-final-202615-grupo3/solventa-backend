import json

import httpx
import pytest

from tests.conftest import (
    BASE, CLIENTE, COTIZACION, IDENTITY, OTRO, QUOTING, SOCIO, VERIFICACION,
)


async def test_registra_prospecto_en_nombre_del_socio(bff, headers_cliente):
    client, backend = bff
    ruta = f"{IDENTITY}/socios/{SOCIO}/prospectos"
    backend.responder("POST", ruta, httpx.Response(201, json={"id": str(CLIENTE)}))
    payload = {"numero_identificacion": "1234567890", "correo": "cliente@example.com"}
    response = await client.post(f"{BASE}/clientes/prospectos", json=payload, headers=headers_cliente)

    assert response.status_code == 201
    assert response.json() == {"id": str(CLIENTE)}
    assert [(r.method, r.url.path) for r in backend.llamadas] == [
        ("POST", f"{IDENTITY}/socios/validar-api-key"), ("POST", ruta)
    ]
    request = backend.llamadas[-1]
    assert json.loads(request.content) == payload
    assert request.headers["x-correlation-id"] == "corr-1"
    assert "x-api-key" not in request.headers and "authorization" not in request.headers


@pytest.mark.parametrize(
    ("metodo", "suffix", "payload"),
    [("GET", "/perfil", None), ("PUT", "/consentimiento", {"estado": "ACEPTADO"})],
)
async def test_consulta_y_actualiza_cliente(bff, headers_cliente, metodo, suffix, payload):
    client, backend = bff
    ruta = f"{IDENTITY}/clientes/{CLIENTE}{suffix}"
    backend.responder(metodo, ruta, httpx.Response(200, json={"cliente_id": str(CLIENTE)}))
    response = await client.request(metodo, f"{BASE}/clientes/{CLIENTE}{suffix}", json=payload, headers=headers_cliente)

    assert response.status_code == 200
    assert response.json()["cliente_id"] == str(CLIENTE)
    request = backend.llamadas[-1]
    assert request.url.path == ruta and request.method == metodo
    if payload is not None:
        assert json.loads(request.content) == payload
    assert "x-api-key" not in request.headers and "authorization" not in request.headers


async def test_inicia_verificacion_y_reenvia_documentos(bff, headers_cliente):
    client, backend = bff
    ruta = f"{IDENTITY}/clientes/{CLIENTE}/verificaciones-kyc-aml"
    backend.responder("POST", ruta, httpx.Response(202, json={"verificacion_id": str(VERIFICACION)}))
    response = await client.post(
        f"{BASE}/clientes/{CLIENTE}/verificaciones-kyc-aml",
        data={"cotizacion_id": str(COTIZACION)},
        files={"documento_frontal": ("doc.jpg", b"frontal", "image/jpeg"),
               "documento_reverso": ("doc2.jpg", b"reverso", "image/jpeg")},
        headers=headers_cliente,
    )
    assert response.status_code == 202
    assert response.json()["verificacion_id"] == str(VERIFICACION)
    assert any(r.url.path == f"{QUOTING}/cotizaciones/{COTIZACION}" for r in backend.llamadas)
    request = backend.llamadas[-1]
    assert request.url.path == ruta
    assert b"frontal" in request.content and b"reverso" in request.content
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert request.headers["idempotency-key"] == "idempotencia-1"


async def test_consulta_verificacion_existente(bff, headers_cliente):
    client, backend = bff
    ruta = f"{IDENTITY}/clientes/{CLIENTE}/verificaciones-kyc-aml/{VERIFICACION}"
    backend.responder("GET", ruta, httpx.Response(200, json={"estado": "APROBADO"}))
    response = await client.get(
        f"{BASE}/clientes/{CLIENTE}/verificaciones-kyc-aml/{VERIFICACION}", headers=headers_cliente
    )
    assert response.status_code == 200 and response.json() == {"estado": "APROBADO"}
    assert backend.llamadas[-1].url.path == ruta
    assert backend.llamadas[-1].headers["x-correlation-id"] == "corr-1"


async def test_verificacion_sin_cotizacion_reenvia_error_del_backend(bff, headers_cliente):
    client, backend = bff
    ruta = f"{IDENTITY}/clientes/{CLIENTE}/verificaciones-kyc-aml"
    detail = {"codigo": "DOCUMENTOS_INCOMPLETOS"}
    backend.responder("POST", ruta, httpx.Response(422, json={"detail": detail}))
    response = await client.post(
        f"{BASE}/clientes/{CLIENTE}/verificaciones-kyc-aml",
        files={"documento_frontal": ("doc.jpg", b"frontal", "image/jpeg")},
        headers=headers_cliente,
    )
    assert response.status_code == 422 and response.json() == {"detail": detail}
    assert backend.llamadas[-1].url.path == ruta
    assert not any(r.url.path.startswith(QUOTING) for r in backend.llamadas)


async def test_cliente_de_ruta_distinto_del_autorizado_no_se_reenvia(bff, headers_cliente):
    client, backend = bff
    response = await client.get(f"{BASE}/clientes/{OTRO}/perfil", headers=headers_cliente)
    assert response.status_code == 403
    assert not any(r.url.path.endswith("/perfil") for r in backend.llamadas)


async def test_verificacion_rechaza_cotizacion_duplicada(bff, headers_cliente):
    client, backend = bff
    response = await client.post(
        f"{BASE}/clientes/{CLIENTE}/verificaciones-kyc-aml",
        files=[
            ("cotizacion_id", (None, str(COTIZACION))),
            ("cotizacion_id", (None, str(COTIZACION))),
            ("documento_frontal", ("doc.jpg", b"doc", "image/jpeg")),
        ],
        headers=headers_cliente,
    )
    assert response.status_code == 422
    assert not any(r.url.path.endswith("/verificaciones-kyc-aml") for r in backend.llamadas)


async def test_registro_propaga_error_estructurado(bff, headers_cliente):
    client, backend = bff
    detail = {"codigo": "DOCUMENTO_DUPLICADO"}
    backend.responder("POST", f"{IDENTITY}/socios/{SOCIO}/prospectos", httpx.Response(409, json={"detail": detail}))
    response = await client.post(f"{BASE}/clientes/prospectos", json={}, headers=headers_cliente)
    assert response.status_code == 409 and response.json() == {"detail": detail}
