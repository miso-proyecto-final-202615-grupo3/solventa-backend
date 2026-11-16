import pytest
from httpx import ASGITransport, AsyncClient

from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError
from src.main import app
from src.presentation.dependencies import get_identity_service_gateway

CLIENTE_ID = "95b19edf-6c4b-4437-99db-d84d0ef482fc"
VERIFICACION_ID = "0f5d2a4e-3a54-4b0e-9a3b-8d6e2f1c7a10"
URL = f"/api/v1/bff-web/clientes/{CLIENTE_ID}/verificaciones-kyc-aml"


class FakeGateway:
    def __init__(self):
        self.error = None
        self.llamadas = []

    async def iniciar_verificacion_kyc_aml(self, cliente_id, payload, content_type, headers=None):
        if self.error:
            raise self.error
        self.llamadas.append(("POST", cliente_id, payload, content_type, headers))
        return {"verificacion_id": VERIFICACION_ID, "estado": "INICIADA", "fecha": "2026-11-08T10:00:00Z"}

    async def consultar_verificacion_kyc_aml(self, cliente_id, verificacion_id, headers=None):
        if self.error:
            raise self.error
        self.llamadas.append(("GET", cliente_id, verificacion_id, headers))
        return {"verificacion_id": verificacion_id, "estado": "APROBADO"}


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
async def client(gateway):
    app.dependency_overrides[get_identity_service_gateway] = lambda: gateway
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_inicia_verificacion_reenviando_archivos_y_cabeceras(client, gateway):
    response = await client.post(
        URL,
        files={
            "documento_frontal": ("f.jpg", b"\xff\xd8\xff1", "image/jpeg"),
            "documento_reverso": ("r.jpg", b"\xff\xd8\xff2", "image/jpeg"),
        },
        headers={"Idempotency-Key": "k-1", "X-Correlation-Id": "corr-1", "Authorization": "secreto"},
    )

    assert response.status_code == 202
    assert response.json()["estado"] == "INICIADA"
    metodo, cliente_id, payload, content_type, headers = gateway.llamadas[0]
    assert cliente_id == CLIENTE_ID
    assert b"\xff\xd8\xff1" in payload and b"\xff\xd8\xff2" in payload
    assert content_type.startswith("multipart/form-data")
    assert headers == {"idempotency-key": "k-1", "x-correlation-id": "corr-1"}


async def test_rechaza_cuerpos_demasiado_grandes_sin_reenviar(client, gateway):
    response = await client.post(
        URL,
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(50 * 1024 * 1024)},
    )

    assert response.status_code == 413
    assert gateway.llamadas == []


async def test_propaga_errores_de_identity(client, gateway):
    gateway.error = IdentityGatewayError(422, {"codigo": "DOCUMENTOS_INCOMPLETOS", "mensaje": "x"})

    response = await client.post(URL, files={"a": ("a", b"1", "image/jpeg")})

    assert response.status_code == 422
    assert response.json()["detail"]["codigo"] == "DOCUMENTOS_INCOMPLETOS"


async def test_consulta_verificacion(client, gateway):
    response = await client.get(f"{URL}/{VERIFICACION_ID}", headers={"X-Correlation-Id": "c"})

    assert response.status_code == 200
    assert response.json() == {"verificacion_id": VERIFICACION_ID, "estado": "APROBADO"}
    assert gateway.llamadas[0][3] == {"x-correlation-id": "c"}


async def test_consulta_propaga_404(client, gateway):
    gateway.error = IdentityGatewayError(404, {"codigo": "VERIFICACION_NO_ENCONTRADA", "mensaje": "x"})

    response = await client.get(f"{URL}/{VERIFICACION_ID}")

    assert response.status_code == 404
