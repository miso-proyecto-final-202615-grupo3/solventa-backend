import pytest

from src.application.ports.identity_provider import (
    AutenticarResult,
    IdentityProviderError,
    InvalidCredentialsError,
)
from src.application.use_cases.autenticar_cliente_use_case import (
    AutenticarClienteUseCase,
)
from src.presentation.schemas import PasswordVerify

CREDENCIALES = PasswordVerify(
    correo="ana.perez@example.com", password="Secreta123"
)


async def test_autentica_y_devuelve_token(fake_identity_provider):
    use_case = AutenticarClienteUseCase(fake_identity_provider)

    resultado = await use_case.ejecutar(CREDENCIALES)

    assert isinstance(resultado, AutenticarResult)
    assert resultado.access_token == "access-123"
    assert resultado.token_type == "Bearer"


async def test_propaga_credenciales_invalidas(fake_identity_provider):
    fake_identity_provider.credenciales_invalidas = True
    use_case = AutenticarClienteUseCase(fake_identity_provider)

    with pytest.raises(InvalidCredentialsError):
        await use_case.ejecutar(CREDENCIALES)


async def test_propaga_error_de_proveedor(fake_identity_provider):
    fake_identity_provider.fallar_autenticacion = True
    use_case = AutenticarClienteUseCase(fake_identity_provider)

    with pytest.raises(IdentityProviderError):
        await use_case.ejecutar(CREDENCIALES)