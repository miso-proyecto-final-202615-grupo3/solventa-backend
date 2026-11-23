import httpx
import pytest

from tests.conftest import BASE, CLIENTE, COTIZACION, OTRO, POLICIES, QUOTING


@pytest.mark.parametrize("suffix", ["/firma-digital", "/poliza"])
async def test_consulta_firma_y_poliza_por_cotizacion(bff, headers_cliente, suffix):
    client, backend = bff
    ruta = f"{POLICIES}/cotizaciones/{COTIZACION}{suffix}"
    backend.responder("GET", ruta, httpx.Response(200, json={"estado": "ACTIVA"}))
    response = await client.get(f"{BASE}/cotizaciones/{COTIZACION}{suffix}", headers=headers_cliente)

    assert response.status_code == 200 and response.json() == {"estado": "ACTIVA"}
    assert backend.llamadas[-2].url.path == f"{QUOTING}/cotizaciones/{COTIZACION}"
    request = backend.llamadas[-1]
    assert request.method == "GET" and request.url.path == ruta
    assert request.headers["x-client-id"] == str(CLIENTE)
    assert "x-api-key" not in request.headers and "authorization" not in request.headers


async def test_captura_firma_con_archivo_y_cabeceras(bff, headers_cliente):
    client, backend = bff
    ruta = f"{POLICIES}/cotizaciones/{COTIZACION}/firma-digital"
    backend.responder("POST", ruta, httpx.Response(201, json={"estado": "FIRMADA"}))
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/firma-digital", headers=headers_cliente,
        data={"cliente_id": str(CLIENTE)}, files={"firma": ("firma.png", b"imagen", "image/png")},
    )
    assert response.status_code == 201 and response.json() == {"estado": "FIRMADA"}
    request = backend.llamadas[-1]
    assert request.method == "POST" and request.url.path == ruta
    assert b"imagen" in request.content and str(CLIENTE).encode() in request.content
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert request.headers["x-client-id"] == str(CLIENTE)
    assert request.headers["idempotency-key"] == "idempotencia-1"
    assert request.headers["x-correlation-id"] == "corr-1"


@pytest.mark.parametrize("cliente", [None, str(OTRO)])
async def test_firma_rechaza_cliente_ausente_o_distinto(bff, headers_cliente, cliente):
    client, backend = bff
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/firma-digital", headers=headers_cliente,
        data={"cliente_id": cliente} if cliente else {},
        files={"firma": ("firma.png", b"imagen", "image/png")},
    )
    assert response.status_code == 403
    assert not any(r.url.path.startswith(POLICIES) for r in backend.llamadas)


async def test_firma_rechaza_clientes_duplicados(bff, headers_cliente):
    client, backend = bff
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/firma-digital", headers=headers_cliente,
        files=[("cliente_id", (None, str(CLIENTE))), ("cliente_id", (None, str(CLIENTE))),
               ("firma", ("firma.png", b"imagen", "image/png"))],
    )
    assert response.status_code == 403
    assert not any(r.url.path.startswith(POLICIES) for r in backend.llamadas)


@pytest.mark.parametrize(("metodo", "suffix"), [("GET", "/poliza"), ("GET", "/firma-digital"), ("POST", "/firma-digital")])
async def test_cotizacion_ajena_bloquea_firma_y_poliza(bff, headers_cliente, metodo, suffix):
    client, backend = bff
    backend.cotizacion["cliente_id"] = str(OTRO)
    response = await client.request(metodo, f"{BASE}/cotizaciones/{COTIZACION}{suffix}", headers=headers_cliente)
    assert response.status_code == 403
    assert not any(r.url.path.startswith(POLICIES) for r in backend.llamadas)


async def test_firma_rechaza_archivo_que_excede_limite(bff, headers_cliente):
    client, backend = bff
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/firma-digital", headers=headers_cliente,
        data={"cliente_id": str(CLIENTE)},
        files={"firma": ("firma.png", b"x" * (2 * 1024 * 1024), "image/png")},
    )
    assert response.status_code == 413
    assert not any(r.url.path.startswith(POLICIES) for r in backend.llamadas)


async def test_error_de_firma_se_propaga(bff, headers_cliente):
    client, backend = bff
    ruta = f"{POLICIES}/cotizaciones/{COTIZACION}/firma-digital"
    detail = {"codigo": "FIRMA_INVALIDA"}
    backend.responder("POST", ruta, httpx.Response(422, json={"detail": detail}))
    response = await client.post(
        f"{BASE}/cotizaciones/{COTIZACION}/firma-digital", headers=headers_cliente,
        data={"cliente_id": str(CLIENTE)}, files={"firma": ("firma.png", b"imagen", "image/png")},
    )
    assert response.status_code == 422 and response.json() == {"detail": detail}
