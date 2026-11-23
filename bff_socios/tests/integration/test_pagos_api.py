import json

import httpx
import pytest

from tests.conftest import BASE, CLIENTE, COTIZACION, OTRO, PAGO, PAYMENTS, QUOTING


async def test_resumen_pago_valida_propietario(bff, headers_cliente):
    client, backend = bff
    ruta = f"{PAYMENTS}/cotizaciones/{COTIZACION}/resumen-pago"
    backend.responder("GET", ruta, httpx.Response(200, json={"total": 12345}))
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}/resumen-pago", headers=headers_cliente)

    assert response.status_code == 200 and response.json() == {"total": 12345}
    assert backend.llamadas[-2].url.path == f"{QUOTING}/cotizaciones/{COTIZACION}"
    assert backend.llamadas[-1].method == "GET" and backend.llamadas[-1].url.path == ruta


async def test_crea_pago_con_cuerpo_y_cabeceras(bff, headers_cliente):
    client, backend = bff
    backend.responder("POST", f"{PAYMENTS}/pagos", httpx.Response(201, json={"pago_id": str(PAGO)}))
    payload = {"cliente_id": str(CLIENTE), "cotizacion_id": str(COTIZACION), "metodo": "TARJETA"}
    response = await client.post(f"{BASE}/pagos", headers=headers_cliente, json=payload)

    assert response.status_code == 201 and response.json() == {"pago_id": str(PAGO)}
    request = backend.llamadas[-1]
    assert request.method == "POST" and request.url.path == f"{PAYMENTS}/pagos"
    assert json.loads(request.content) == payload
    assert request.headers["idempotency-key"] == "idempotencia-1"
    assert request.headers["x-correlation-id"] == "corr-1"
    assert "x-api-key" not in request.headers and "authorization" not in request.headers


async def test_consulta_pago_del_cliente(bff, headers_cliente):
    client, backend = bff
    ruta = f"{PAYMENTS}/pagos/{PAGO}"
    data = {"pago_id": str(PAGO), "cliente_id": str(CLIENTE), "estado": "APROBADO"}
    backend.responder("GET", ruta, httpx.Response(200, json=data))
    response = await client.get(f"{BASE}/pagos/{PAGO}", headers=headers_cliente)
    assert response.status_code == 200 and response.json() == data
    assert backend.llamadas[-1].method == "GET" and backend.llamadas[-1].url.path == ruta


@pytest.mark.parametrize(
    ("payload", "codigo"),
    [({"cliente_id": str(OTRO), "cotizacion_id": str(COTIZACION)}, 403),
     ({"cliente_id": "no-es-uuid", "cotizacion_id": str(COTIZACION)}, 422),
     ({"cliente_id": str(CLIENTE), "cotizacion_id": "no-es-uuid"}, 422)],
)
async def test_pago_rechaza_identidades_invalidas(bff, headers_cliente, payload, codigo):
    client, backend = bff
    response = await client.post(f"{BASE}/pagos", headers=headers_cliente, json=payload)
    assert response.status_code == codigo
    assert not any(r.url.path.startswith(PAYMENTS) for r in backend.llamadas)


@pytest.mark.parametrize(("metodo", "suffix"), [("GET", f"/cotizaciones/{COTIZACION}/resumen-pago"), ("POST", "/pagos")])
async def test_pago_rechaza_cotizacion_ajena(bff, headers_cliente, metodo, suffix):
    client, backend = bff
    backend.cotizacion["cliente_id"] = str(OTRO)
    response = await client.request(metodo, f"{BASE}{suffix}", headers=headers_cliente,
                                    json={"cliente_id": str(CLIENTE), "cotizacion_id": str(COTIZACION)})
    assert response.status_code == 403
    assert not any(r.url.path.startswith(PAYMENTS) for r in backend.llamadas)


@pytest.mark.parametrize(
    ("data", "codigo"),
    [({"cliente_id": str(OTRO)}, 403), ({}, 502), ({"cliente_id": "no-es-uuid"}, 502)],
)
async def test_consulta_pago_rechaza_propietario_ajeno_o_invalido(bff, headers_cliente, data, codigo):
    client, backend = bff
    backend.responder("GET", f"{PAYMENTS}/pagos/{PAGO}", httpx.Response(200, json=data))
    response = await client.get(f"{BASE}/pagos/{PAGO}", headers=headers_cliente)
    assert response.status_code == codigo


async def test_consulta_pago_propaga_error_estructurado(bff, headers_cliente):
    client, backend = bff
    detail = {"codigo": "PAGO_NO_ENCONTRADO"}
    backend.responder("GET", f"{PAYMENTS}/pagos/{PAGO}", httpx.Response(404, json={"detail": detail}))
    response = await client.get(f"{BASE}/pagos/{PAGO}", headers=headers_cliente)
    assert response.status_code == 404 and response.json() == {"detail": detail}


async def test_creacion_pago_rechaza_json_invalido_y_cuerpo_excesivo(bff, headers_cliente):
    client, backend = bff
    assert (await client.post(f"{BASE}/pagos", content=b"{", headers=headers_cliente)).status_code == 422
    assert (await client.post(f"{BASE}/pagos", content=b"x" * (1024 * 1024 + 1), headers=headers_cliente)).status_code == 413
    assert not any(r.url.path.startswith(PAYMENTS) for r in backend.llamadas)


async def test_creacion_pago_propaga_conflicto(bff, headers_cliente):
    client, backend = bff
    detail = {"codigo": "PAGO_DUPLICADO"}
    backend.responder("POST", f"{PAYMENTS}/pagos", httpx.Response(409, json={"detail": detail}))
    response = await client.post(
        f"{BASE}/pagos", headers=headers_cliente,
        json={"cliente_id": str(CLIENTE), "cotizacion_id": str(COTIZACION)},
    )
    assert response.status_code == 409 and response.json() == {"detail": detail}
