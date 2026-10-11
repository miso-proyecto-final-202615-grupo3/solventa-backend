from src.core.config import settings
from src.infrastructure.gateways.cognito_identity_provider import (
    CognitoIdentityProvider,
)
from src.infrastructure.gateways.noop_identity_provider import NoopIdentityProvider
from src.presentation.dependencies import get_identity_provider


async def test_get_identity_provider_devuelve_noop_por_defecto(monkeypatch):
    monkeypatch.setattr(settings, "COGNITO_ENABLED", False)

    assert isinstance(get_identity_provider(), NoopIdentityProvider)


async def test_get_identity_provider_devuelve_cognito_cuando_esta_habilitado(
    monkeypatch,
):
    monkeypatch.setattr(settings, "COGNITO_ENABLED", True)

    assert isinstance(get_identity_provider(), CognitoIdentityProvider)