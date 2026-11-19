import json
from uuid import uuid4

import httpx
import pytest

from src.main import app
from src.presentation.dependencies import get_http_client

BASE = "/api/v1/bff-socios"
SOCIO = str(uuid4())
CLIENTE = str(uuid4())
OTRO = str(uuid4())
COTIZACION = str(uuid4())


@pytest.fixture
async def api():
    seen = []
    state = {"associated": True, "owner": CLIENTE, "unavailable": False, "invalid_identity": False}

    def handler(request):
        seen.append(request)
        if state["unavailable"]:
            raise httpx.ConnectError("no disponible", request=request)
        path = request.url.path
        if path.endswith("/socios/validar-api-key"):
            if state["invalid_identity"]:
                return httpx.Response(200, text="respuesta inválida")
            return httpx.Response(200, json={"socio_id": SOCIO}) if json.loads(request.content)["api_key"] == "valida" else httpx.Response(401, json={"detail": "API key inválida."})
        if path.endswith("/autorizacion"):
            return httpx.Response(204) if state["associated"] else httpx.Response(403, json={"detail": "No autorizado."})
        if path.endswith(f"/cotizaciones/{COTIZACION}") and request.method == "GET":
            return httpx.Response(200, json={"cliente_id": state["owner"]})
        if path.endswith("/cotizaciones") and request.method == "POST":
            return httpx.Response(201, json=json.loads(request.content))
        if path.endswith(f"/socios/{SOCIO}/prospectos"):
            return httpx.Response(201, json={"id": CLIENTE})
        if path.endswith("/certificado/descarga"):
            return httpx.Response(
                200, content=b"%PDF-test", headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="certificado.pdf"',
                    "cache-control": "private, no-store",
                },
            )
        if "/payments-service/pagos/" in path:
            return httpx.Response(200, json={"cliente_id": state["owner"]})
        if path.endswith("/pagos") and request.method == "POST":
            return httpx.Response(201, json=json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as backend:
        app.dependency_overrides[get_http_client] = lambda: backend
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, state, seen
    app.dependency_overrides.clear()


async def test_rechaza_claves_y_clientes_no_asociados(api):
    client, state, _ = api
    url = f"{BASE}/cotizaciones/{COTIZACION}"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers={"X-API-Key": "invalida", "X-Client-Id": CLIENTE})).status_code == 401
    state["associated"] = False
    assert (await client.get(url, headers={"X-API-Key": "valida", "X-Client-Id": CLIENTE})).status_code == 403


async def test_cotizacion_vincula_socio_y_verifica_propietario(api):
    client, state, seen = api
    headers = {"X-API-Key": "valida", "X-Client-Id": CLIENTE}
    response = await client.post(f"{BASE}/cotizaciones", headers=headers, json={"cliente_id": CLIENTE, "producto_codigo": "VIDA"})
    assert response.status_code == 201
    assert response.json()["socio_id"] == SOCIO
    assert (await client.post(f"{BASE}/cotizaciones", headers=headers, json={"cliente_id": OTRO, "producto_codigo": "VIDA"})).status_code == 403
    state["owner"] = OTRO
    before = len(seen)
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}/condiciones", headers=headers)
    assert response.status_code == 403
    assert all(not req.url.path.endswith("/condiciones") for req in seen[before:])
    assert all("x-api-key" not in req.headers for req in seen)


async def test_multipart_y_pago_validan_cliente_y_cotizacion(api):
    client, state, seen = api
    headers = {"X-API-Key": "valida", "X-Client-Id": CLIENTE, "Idempotency-Key": "intento-1"}
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/firma-digital", headers=headers,
        data={"cliente_id": CLIENTE, "producto_id": str(uuid4())}, files={"firma": ("firma.png", b"firma", "image/png")},
    )
    assert response.status_code == 200
    firma = seen[-1]
    assert firma.headers["idempotency-key"] == "intento-1"
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/firma-digital", headers=headers,
        data={"cliente_id": OTRO, "producto_id": str(uuid4())}, files={"firma": ("firma.png", b"firma", "image/png")},
    )
    assert response.status_code == 403
    state["owner"] = OTRO
    response = await client.post(f"{BASE}/pagos", headers=headers, json={"cliente_id": CLIENTE, "cotizacion_id": COTIZACION})
    assert response.status_code == 403


async def test_verificacion_no_acepta_cotizacion_ajena(api):
    client, state, _ = api
    state["owner"] = OTRO
    response = await client.post(
        f"{BASE}/clientes/{CLIENTE}/verificaciones-kyc-aml",
        headers={"X-API-Key": "valida", "X-Client-Id": CLIENTE},
        data={"cotizacion_id": COTIZACION},
        files={"documento_frontal": ("doc.jpg", b"doc", "image/jpeg")},
    )
    assert response.status_code == 403


async def test_pago_y_consulta_de_emision_del_cliente(api):
    client, state, seen = api
    headers = {"X-API-Key": "valida", "X-Client-Id": CLIENTE, "Idempotency-Key": "pago-1"}
    response = await client.post(f"{BASE}/pagos", headers=headers, json={"cliente_id": CLIENTE, "cotizacion_id": COTIZACION})
    assert response.status_code == 201
    assert seen[-1].headers["idempotency-key"] == "pago-1"
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}/poliza", headers=headers)
    assert response.status_code == 200
    assert seen[-1].headers["x-client-id"] == CLIENTE
    response = await client.get(f"{BASE}/polizas/mis-polizas", headers=headers)
    assert response.status_code == 200
    pago_id = uuid4()
    state["owner"] = OTRO
    assert (await client.get(f"{BASE}/pagos/{pago_id}", headers=headers)).status_code == 403


async def test_prospecto_y_certificado_conservan_respuestas_y_cabeceras(api):
    client, _, seen = api
    headers = {"X-API-Key": "valida", "X-Client-Id": CLIENTE}
    payload = {"numero_identificacion": "1234567890"}
    response = await client.post(f"{BASE}/clientes/prospectos", headers=headers, json=payload)
    assert response.status_code == 201
    assert response.json() == {"id": CLIENTE}
    assert json.loads(seen[-1].content) == payload
    assert "x-api-key" not in seen[-1].headers

    response = await client.get(f"{BASE}/polizas/{uuid4()}/certificado/descarga", headers=headers)
    assert response.content == b"%PDF-test"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="certificado.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert seen[-1].headers["x-client-id"] == CLIENTE


async def test_errores_del_backend_no_permiten_continuar(api):
    client, state, _ = api
    headers = {"X-API-Key": "valida", "X-Client-Id": CLIENTE}
    state["invalid_identity"] = True
    response = await client.get(f"{BASE}/productos", headers=headers)
    assert response.status_code == 502
    assert response.json()["detail"] == "Respuesta inválida del servicio de backend."
    state["invalid_identity"] = False
    state["unavailable"] = True
    response = await client.get(f"{BASE}/productos", headers=headers)
    assert response.status_code == 503
    assert response.json()["detail"] == "Servicio de backend no disponible."


async def test_rutas_de_cliente_y_decisiones_preservan_sufijo_y_cuerpo(api):
    client, _, seen = api
    headers = {"X-API-Key": "valida", "X-Client-Id": CLIENTE, "Idempotency-Key": "decision-1"}
    response = await client.get(f"{BASE}/clientes/{CLIENTE}/perfil", headers=headers)
    assert response.status_code == 200
    assert seen[-1].url.path.endswith(f"/clientes/{CLIENTE}/perfil")
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/condiciones/decisiones",
        headers=headers,
        json={"decision": "ACEPTADA"},
    )
    assert response.status_code == 200
    assert seen[-1].url.path.endswith(f"/cotizaciones/{COTIZACION}/condiciones/decisiones")
    assert json.loads(seen[-1].content) == {"decision": "ACEPTADA"}
    assert seen[-1].headers["idempotency-key"] == "decision-1"
