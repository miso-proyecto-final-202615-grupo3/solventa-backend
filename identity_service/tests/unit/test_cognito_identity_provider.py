import pytest
from botocore.exceptions import ClientError

import src.infrastructure.gateways.cognito_identity_provider as mod
from src.application.use_cases.registrar_cliente_use_case import IdentityProviderError
from src.infrastructure.gateways.cognito_identity_provider import CognitoIdentityProvider


class FakeCognitoClient:
    def __init__(self):
        self.created: list[dict] = []
        self.passwords: list[dict] = []
        self.deleted: list[dict] = []
        self.fail_crear: bool = False

    def admin_create_user(self, **kwargs):
        if self.fail_crear:
            raise ClientError(
                {
                    "Error": {
                        "Code": "UsernameExistsException",
                        "Message": "el usuario ya existe",
                    },
                    "ResponseMetadata": {},
                },
                "AdminCreateUser",
            )
        self.created.append(kwargs)
        return {"User": {"Username": kwargs["Username"]}}

    def admin_set_user_password(self, **kwargs):
        self.passwords.append(kwargs)

    def admin_delete_user(self, **kwargs):
        self.deleted.append(kwargs)


@pytest.fixture
def provider(monkeypatch):
    async def fake_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    client = FakeCognitoClient()
    monkeypatch.setattr(mod, "run_in_threadpool", fake_run_in_threadpool)
    monkeypatch.setattr(mod.boto3, "client", lambda service, region_name: client)

    identity = CognitoIdentityProvider(
        user_pool_id="pool-1", region_name="us-east-1"
    )
    return identity, client


async def test_registra_usuario_crea_credencial(provider):
    identity, client = provider

    await identity.registrar_usuario("ana@example.com", "Secreta123")

    assert client.created[0]["UserPoolId"] == "pool-1"
    assert client.created[0]["Username"] == "ana@example.com"
    assert client.passwords[0]["Username"] == "ana@example.com"
    assert client.passwords[0]["Password"] == "Secreta123"
    assert client.passwords[0]["Permanent"] is True


async def test_registra_usuario_envuelve_error_de_cognito(provider):
    identity, client = provider
    client.fail_crear = True

    with pytest.raises(IdentityProviderError):
        await identity.registrar_usuario("ana@example.com", "Secreta123")


async def test_elimina_usuario_de_cognito(provider):
    identity, client = provider

    await identity.eliminar_usuario("ana@example.com")

    assert client.deleted[0]["Username"] == "ana@example.com"