import json

import httpx
import pytest

from tests.conftest import BASE, CLIENTE, COTIZACION, IDENTITY, OTRO, QUOTING, SOCIO


@pytest.mark.parametrize("suffix", ["/productos", "/productos/VIDA"])
async def test_consulta_productos(bff, headers_cliente, suffix):
    client, backend = bff
    backend.responder("GET", f"{QUOTING}{suffix}", httpx.Response(200, json={"producto": "VIDA"}))
    response = await client.get(f"{BASE}{suffix}", headers=headers_cliente)

    assert response.status_code == 200 and response.json() == {"producto": "VIDA"}
    assert [(r.method, r.url.path) for r in backend.llamadas] == [
        ("POST", f"{IDENTITY}/socios/validar-api-key"), ("GET", f"{QUOTING}{suffix}")
    ]
    assert backend.llamadas[-1].headers["x-correlation-id"] == "corr-1"
    assert "x-api-key" not in backend.llamadas[-1].headers


async def test_crea_cotizacion_con_socio_autenticado(bff, headers_cliente):
    client, backend = bff
    ruta = f"{QUOTING}/cotizaciones"
    backend.responder("POST", ruta, httpx.Response(201, json={"cotizacion_id": str(COTIZACION)}))
    payload = {"cliente_id": str(CLIENTE), "producto_codigo": "VIDA"}
    response = await client.post(f"{BASE}/cotizaciones", json=payload, headers=headers_cliente)

    assert response.status_code == 201 and response.json()["cotizacion_id"] == str(COTIZACION)
    request = backend.llamadas[-1]
    assert request.method == "POST" and request.url.path == ruta
    assert json.loads(request.content) == {**payload, "socio_id": str(SOCIO)}
    assert request.headers["content-type"] == "application/json"
    assert request.headers["idempotency-key"] == "idempotencia-1"
    assert "x-api-key" not in request.headers and "authorization" not in request.headers


@pytest.mark.parametrize(
    ("metodo", "suffix", "payload", "codigo"),
    [("GET", "", None, 200), ("GET", "/condiciones", None, 200),
     ("POST", "/condiciones/decisiones", {"decision": "ACEPTADA"}, 201)],
)
async def test_operaciones_cotizacion_validan_propietario_y_reenvian(
    bff, headers_cliente, metodo, suffix, payload, codigo
):
    client, backend = bff
    ruta = f"{QUOTING}/cotizaciones/{COTIZACION}{suffix}"
    resultado = {"resultado": "ok"} if suffix else backend.cotizacion
    backend.responder(metodo, ruta, httpx.Response(codigo, json=resultado))
    response = await client.request(metodo, f"{BASE}/cotizaciones/{COTIZACION}{suffix}", json=payload, headers=headers_cliente)

    assert response.status_code == codigo and response.json() == resultado
    requests_quoting = [r for r in backend.llamadas if r.url.path.startswith(QUOTING)]
    assert requests_quoting[0].method == "GET"
    assert requests_quoting[0].url.path == f"{QUOTING}/cotizaciones/{COTIZACION}"
    assert requests_quoting[-1].method == metodo and requests_quoting[-1].url.path == ruta
    assert len(requests_quoting) == 2
    if payload is not None:
        assert json.loads(requests_quoting[-1].content) == payload
        assert requests_quoting[-1].headers["idempotency-key"] == "idempotencia-1"


@pytest.mark.parametrize(
    ("payload", "codigo"),
    [({"cliente_id": str(OTRO)}, 403),
     ({"cliente_id": str(CLIENTE), "socio_id": str(OTRO)}, 403),
     ({"cliente_id": "no-es-uuid"}, 422),
     ({"cliente_id": str(CLIENTE), "socio_id": "no-es-uuid"}, 422)],
)
async def test_creacion_rechaza_identidades_invalidas(bff, headers_cliente, payload, codigo):
    client, backend = bff
    response = await client.post(f"{BASE}/cotizaciones", json=payload, headers=headers_cliente)
    assert response.status_code == codigo
    assert not any(r.url.path == f"{QUOTING}/cotizaciones" for r in backend.llamadas)


async def test_rechaza_json_invalido_y_cuerpo_excesivo(bff, headers_cliente):
    client, backend = bff
    assert (await client.post(f"{BASE}/cotizaciones", content=b"{", headers=headers_cliente)).status_code == 422
    assert (await client.post(f"{BASE}/cotizaciones", content=b"x" * (1024 * 1024 + 1), headers=headers_cliente)).status_code == 413
    assert not any(r.url.path == f"{QUOTING}/cotizaciones" for r in backend.llamadas)


@pytest.mark.parametrize("suffix", ["/condiciones", "/condiciones/decisiones"])
async def test_cotizacion_ajena_no_se_reenvia(bff, headers_cliente, suffix):
    client, backend = bff
    backend.cotizacion["cliente_id"] = str(OTRO)
    metodo = "POST" if suffix.endswith("decisiones") else "GET"
    response = await client.request(metodo, f"{BASE}/cotizaciones/{COTIZACION}{suffix}", headers=headers_cliente)
    assert response.status_code == 403
    assert not any(r.url.path.endswith(suffix) for r in backend.llamadas)


async def test_error_de_condiciones_se_propaga(bff, headers_cliente):
    client, backend = bff
    ruta = f"{QUOTING}/cotizaciones/{COTIZACION}/condiciones"
    backend.responder("GET", ruta, httpx.Response(404, json={"detail": {"codigo": "NO_ENCONTRADA"}}))
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}/condiciones", headers=headers_cliente)
    assert response.status_code == 404 and response.json() == {"detail": {"codigo": "NO_ENCONTRADA"}}


@pytest.mark.parametrize("data", [{}, {"cliente_id": "no-es-uuid"}])
async def test_respuesta_invalida_de_propietario_rechaza_operacion(bff, headers_cliente, data):
    client, backend = bff
    backend.cotizacion = data
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}/condiciones", headers=headers_cliente)
    assert response.status_code == 502
    assert not any(r.url.path.endswith("/condiciones") for r in backend.llamadas)
