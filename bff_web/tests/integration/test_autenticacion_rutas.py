import re
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from src.core.config import settings
from src.main import app
from src.presentation import cliente_jwt_validator, dependencies
from src.presentation.auditor_jwt_validator import AuditorTokenError
from src.presentation.cliente_jwt_validator import ClienteTokenError, CognitoClienteJwtValidator
from src.presentation.dependencies import (
    get_identity_service_gateway,
    get_quotingengine_service_gateway,
)
from src.presentation.socios_admin_jwt_validator import SociosAdminTokenError

BASE = settings.API_PREFIX
ID = "00000000-0000-0000-0000-000000000001"
PUBLICAS = {
    ("POST", f"{BASE}/clientes/registro"): 201,
    ("POST", f"{BASE}/clientes/autenticar"): 200,
    ("POST", f"{BASE}/clientes/recuperar-clave"): 202,
    ("POST", f"{BASE}/clientes/recuperar-clave/confirmar"): 200,
    ("GET", f"{BASE}/productos"): 200,
    ("GET", f"{BASE}/productos/{{codigo}}"): 200,
}


def rutas_api():
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(f"{BASE}/")
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }


def ruta_con_parametros(path):
    return re.sub(r"\{[^}]+\}", ID, path)


@pytest.fixture
def gateways():
    class Identidad:
        llamadas = []

        async def obtener_perfil_cliente(self, cliente_id):
            self.llamadas.append(("perfil", cliente_id))
            return {"id": cliente_id}

        async def registrar_cliente(self, payload, content_type):
            self.llamadas.append(("registro", payload))
            return {}

        async def autenticar_cliente(self, payload, content_type):
            self.llamadas.append(("autenticar", payload))
            return {}

        async def solicitar_recuperacion_clave(self, payload, content_type):
            self.llamadas.append(("recuperar", payload))
            return {}

        async def confirmar_recuperacion_clave(self, payload, content_type):
            self.llamadas.append(("confirmar", payload))
            return {}

    class Cotizacion:
        llamadas = []

        async def listar_productos(self):
            self.llamadas.append(("listar",))
            return [{"codigo": "VIDA"}]

        async def obtener_producto(self, codigo):
            self.llamadas.append(("obtener", codigo))
            return {"codigo": codigo}

    identidad, cotizacion = Identidad(), Cotizacion()
    app.dependency_overrides[get_identity_service_gateway] = lambda: identidad
    app.dependency_overrides[get_quotingengine_service_gateway] = lambda: cotizacion
    try:
        yield identidad, cotizacion
    finally:
        app.dependency_overrides.pop(get_identity_service_gateway, None)
        app.dependency_overrides.pop(get_quotingengine_service_gateway, None)


def test_excepciones_publicas_existen():
    assert PUBLICAS.keys() <= rutas_api()


@pytest.mark.parametrize(("method", "path"), sorted(rutas_api() - PUBLICAS.keys()))
@pytest.mark.parametrize("authorization", [None, "Bearer invalido"])
async def test_todas_las_demas_rutas_exigen_jwt(async_client, monkeypatch, method, path, authorization):
    class Validator:
        def __init__(self, error):
            self.error = error

        def validar(self, token):
            raise self.error()

    monkeypatch.setattr(dependencies, "get_cognito_cliente_jwt_validator", lambda: Validator(ClienteTokenError))
    monkeypatch.setattr(dependencies, "get_cognito_auditor_jwt_validator", lambda: Validator(AuditorTokenError))
    monkeypatch.setattr(dependencies, "get_cognito_socios_admin_jwt_validator", lambda: Validator(SociosAdminTokenError))
    headers = {"Authorization": authorization} if authorization else {}
    response = await async_client.request(method, ruta_con_parametros(path), headers=headers)
    assert response.status_code == 401, (method, path, response.text)


@pytest.mark.parametrize(("method", "path", "status"), [
    (method, path, status) for (method, path), status in PUBLICAS.items()
])
@pytest.mark.parametrize("authorization", [None, "Bearer invalido"])
async def test_rutas_publicas_no_validan_token(async_client, monkeypatch, gateways, method, path, status, authorization):
    def no_validar():
        pytest.fail("Una ruta pública no debe consultar el validador JWT")

    monkeypatch.setattr(dependencies, "get_cognito_cliente_jwt_validator", no_validar)
    headers = {"Authorization": authorization} if authorization else {}
    response = await async_client.request(method, ruta_con_parametros(path), headers=headers)
    assert response.status_code == status
    identidad, cotizacion = gateways
    assert len(identidad.llamadas) + len(cotizacion.llamadas) == 1


async def test_ruta_protegida_verifica_firma_y_vencimiento(async_client, monkeypatch, gateways):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class Jwks:
        def get_signing_key_from_jwt(self, token):
            class Key:
                pass
            result = Key()
            result.key = key.public_key()
            return result

    monkeypatch.setattr(settings, "COGNITO_REGION", "us-east-1")
    monkeypatch.setattr(settings, "COGNITO_USER_POOL_ID", "us-east-1_TEST")
    monkeypatch.setattr(settings, "COGNITO_CLIENT_ID", "web")
    monkeypatch.setattr(cliente_jwt_validator, "PyJWKClient", lambda *args, **kwargs: Jwks())
    validator = CognitoClienteJwtValidator()
    monkeypatch.setattr(dependencies, "get_cognito_cliente_jwt_validator", lambda: validator)
    claims = {
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST",
        "sub": "cliente",
        "token_use": "access",
        "client_id": "web",
        "exp": int(time.time()) + 300,
    }
    valid = jwt.encode(claims, key, algorithm="RS256")
    expired = jwt.encode({**claims, "exp": int(time.time()) - 1}, key, algorithm="RS256")
    bad_signature = jwt.encode(claims, other_key, algorithm="RS256")
    path = f"{BASE}/clientes/{ID}/perfil"
    for token in (expired, bad_signature):
        response = await async_client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
    assert gateways[0].llamadas == []

    response = await async_client.get(path, headers={"Authorization": f"Bearer {valid}"})
    assert response.status_code == 200 and response.json() == {"id": ID}
    assert gateways[0].llamadas == [("perfil", ID)]
