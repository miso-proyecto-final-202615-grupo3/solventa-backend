import httpx
import pytest

from tests.conftest import BASE, CLIENTE, POLICIES, POLIZA


@pytest.mark.parametrize("suffix", ["/mis-polizas", f"/{POLIZA}", f"/{POLIZA}/certificado"])
async def test_consulta_polizas_y_certificado(bff, headers_cliente, suffix):
    client, backend = bff
    ruta = f"{POLICIES}/polizas{suffix}"
    backend.responder("GET", ruta, httpx.Response(200, json={"estado": "ACTIVA"}))
    response = await client.get(f"{BASE}/polizas{suffix}", headers=headers_cliente)

    assert response.status_code == 200 and response.json() == {"estado": "ACTIVA"}
    request = backend.llamadas[-1]
    assert request.method == "GET" and request.url.path == ruta
    assert request.headers["x-client-id"] == str(CLIENTE)
    assert request.headers["x-correlation-id"] == "corr-1"
    assert "x-api-key" not in request.headers and "authorization" not in request.headers


async def test_descarga_pdf_preserva_cuerpo_y_cabeceras(bff, headers_cliente):
    client, backend = bff
    suffix = f"/{POLIZA}/certificado/descarga"
    backend.responder(
        "GET", f"{POLICIES}/polizas{suffix}",
        httpx.Response(200, content=b"%PDF-documento", headers={
            "content-type": "application/pdf",
            "content-disposition": 'attachment; filename="certificado.pdf"',
            "cache-control": "private, no-store",
        }),
    )
    response = await client.get(f"{BASE}/polizas{suffix}", headers=headers_cliente)
    assert response.status_code == 200 and response.content == b"%PDF-documento"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="certificado.pdf"'
    assert response.headers["cache-control"] == "private, no-store"
    assert backend.llamadas[-1].headers["x-client-id"] == str(CLIENTE)


async def test_poliza_inexistente_propaga_respuesta(bff, headers_cliente):
    client, backend = bff
    backend.responder("GET", f"{POLICIES}/polizas/{POLIZA}", httpx.Response(404, json={"detail": "No encontrada"}))
    response = await client.get(f"{BASE}/polizas/{POLIZA}", headers=headers_cliente)
    assert response.status_code == 404 and response.json() == {"detail": "No encontrada"}
