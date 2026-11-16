import httpx
import pytest

from src.infrastructure.gateways.identity_service_gateway import IdentityGatewayError, IdentityServiceGateway
from src.infrastructure.gateways.insuranceclaims_service_gateway import (
    ClaimsGatewayError,
    InsuranceClaimsServiceGateway,
)
from src.presentation.cliente_resolver import ClienteIdResolver, limpiar_cache
from src.presentation.errors import ApiError


class IdentidadFake:
    def __init__(self, error: IdentityGatewayError | None = None) -> None:
        self.llamadas = 0
        self.error = error

    async def obtener_cliente_id(self, correo, correlation_id):
        self.llamadas += 1
        if self.error:
            raise self.error
        return "cliente-1"


@pytest.fixture(autouse=True)
def cache_limpia():
    limpiar_cache()
    yield
    limpiar_cache()


async def test_resolver_usa_cache_por_correo_sin_importar_mayusculas():
    identidad = IdentidadFake()
    resolver = ClienteIdResolver(identidad, ttl_seconds=300)

    assert await resolver.resolver("Ana@Example.com", "c") == "cliente-1"
    assert await resolver.resolver("ana@example.com", "c") == "cliente-1"
    assert identidad.llamadas == 1


async def test_resolver_sin_cache_vuelve_a_consultar():
    identidad = IdentidadFake()
    resolver = ClienteIdResolver(identidad, ttl_seconds=0)

    await resolver.resolver("ana@example.com", "c")
    await resolver.resolver("ana@example.com", "c")

    assert identidad.llamadas == 2


@pytest.mark.parametrize(("status", "codigo"), [(404, "CLIENTE_NO_REGISTRADO"), (503, "SERVICIO_NO_DISPONIBLE")])
async def test_resolver_traduce_errores_de_identidad(status, codigo):
    resolver = ClienteIdResolver(IdentidadFake(IdentityGatewayError(status, "x")))

    with pytest.raises(ApiError) as error:
        await resolver.resolver("ana@example.com", "c")

    assert error.value.codigo == codigo


async def test_identidad_obtener_cliente_id_no_envia_installation_id():
    recibido = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recibido["params"] = dict(request.url.params)
        recibido["corr"] = request.headers["X-Correlation-Id"]
        return httpx.Response(200, json={"id": "abc", "nombre": "Ana", "estado_kyc": "PENDIENTE",
                                         "dispositivo_vinculado": True})

    gateway = IdentityServiceGateway("http://identity", transport=httpx.MockTransport(handler))

    assert await gateway.obtener_cliente_id("ana@example.com", "corr-9") == "abc"
    assert recibido == {"params": {"correo": "ana@example.com"}, "corr": "corr-9"}


async def test_claims_gateway_envia_cliente_clave_correlacion_e_idioma():
    recibido = []

    def handler(request: httpx.Request) -> httpx.Response:
        recibido.append((request.method, request.url.path, dict(request.headers)))
        if request.method == "POST":
            return httpx.Response(200, json={"repetido": True})
        return httpx.Response(200, json={"polizas": []})

    gateway = InsuranceClaimsServiceGateway("http://claims", transport=httpx.MockTransport(handler))

    await gateway.listar_polizas_elegibles("cli", "corr", "en")
    status, body = await gateway.reportar_siniestro("cli", "key", {"a": 1}, "corr")

    assert status == 200 and body == {"repetido": True}
    metodo, path, headers = recibido[0]
    assert path == "/api/v1/insuranceclaims-service/siniestros/polizas-elegibles"
    assert headers["x-cliente-id"] == "cli" and headers["accept-language"] == "en"
    assert recibido[1][2]["idempotency-key"] == "key"


async def test_claims_gateway_errores():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"codigo": "POLIZA_NO_VIGENTE", "mensaje": "x"}})

    gateway = InsuranceClaimsServiceGateway("http://claims", transport=httpx.MockTransport(handler))

    with pytest.raises(ClaimsGatewayError) as error:
        await gateway.obtener_siniestro("cli", "id", "corr")
    assert error.value.status_code == 409
    assert error.value.detail["codigo"] == "POLIZA_NO_VIGENTE"


async def test_claims_gateway_caido_es_503():
    def handler(request):
        raise httpx.ConnectError("caido", request=request)

    gateway = InsuranceClaimsServiceGateway("http://claims", transport=httpx.MockTransport(handler))

    with pytest.raises(ClaimsGatewayError) as error:
        await gateway.listar_polizas_elegibles("cli", "corr")
    assert error.value.status_code == 503
