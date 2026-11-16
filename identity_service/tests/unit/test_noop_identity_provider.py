import pytest

from src.application.ports.identity_provider import (
    IdentityProviderError,
    InvalidCredentialsError,
)
from src.infrastructure.gateways.noop_identity_provider import NoopIdentityProvider


async def test_registrar_usuario_es_noop():
    provider = NoopIdentityProvider()

    await provider.registrar_usuario("ana@example.com", "Secreta123")


async def test_autenticar_usuario_rechaza_sin_proveedor_real():
    provider = NoopIdentityProvider()

    with pytest.raises(InvalidCredentialsError):
        await provider.autenticar_usuario("ana@example.com", "Secreta123")


async def test_eliminar_usuario_es_noop():
    provider = NoopIdentityProvider()

    await provider.eliminar_usuario("ana@example.com")


async def test_recuperacion_requiere_cognito():
    provider = NoopIdentityProvider()

    with pytest.raises(IdentityProviderError):
        await provider.solicitar_recuperacion_clave("ana@example.com")

    with pytest.raises(IdentityProviderError):
        await provider.confirmar_recuperacion_clave(
            "ana@example.com", "123456", "NuevaClave123"
        )
