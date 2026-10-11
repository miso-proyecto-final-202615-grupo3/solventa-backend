import logging

from src.application.ports.identity_provider import (
    AutenticarResult,
    IdentityProvider,
    InvalidCredentialsError,
)

logger = logging.getLogger(__name__)


class NoopIdentityProvider(IdentityProvider):
    """Proveedor de identidad de desarrollo (sin AWS/Cognito).

    Permite probar el flujo de registro en local: las credenciales se
    ignoran y la autenticación no está disponible. El registro queda en la
    BD del MS Identidad, listo para validar el journey completo en desarrollo.
    """

    async def registrar_usuario(self, correo: str, password: str) -> None:
        logger.warning(
            "NoopIdentityProvider: identidad para %s no creada (modo local).",
            correo,
        )

    async def autenticar_usuario(
        self, correo: str, password: str
    ) -> AutenticarResult:
        raise InvalidCredentialsError(
            "Autenticación no disponible en modo local (Cognito no configurado)."
        )

    async def eliminar_usuario(self, correo: str) -> None:
        logger.warning(
            "NoopIdentityProvider: identidad para %s no existe (modo local).",
            correo,
        )