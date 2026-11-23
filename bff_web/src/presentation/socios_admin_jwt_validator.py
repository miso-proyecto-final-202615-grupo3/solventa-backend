from functools import lru_cache

import jwt
from jwt import PyJWKClient

from src.core.config import settings


class SociosAdminTokenError(Exception):
    pass


class SociosAdminTokenConfiguracionError(Exception):
    pass


class CognitoSociosAdminJwtValidator:
    def __init__(self) -> None:
        if (
            not settings.COGNITO_REGION
            or not settings.COGNITO_USER_POOL_ID
            or not settings.COGNITO_CLIENT_ID
        ):
            raise SociosAdminTokenConfiguracionError(
                "Cognito no está configurado para administrar socios."
            )
        self.issuer = (
            f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/"
            f"{settings.COGNITO_USER_POOL_ID}"
        )
        self.jwks = PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=settings.COGNITO_JWKS_TTL_SECONDS,
        )

    def validar(self, token: str) -> str:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"verify_aud": False, "require": ["exp", "iss", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise SociosAdminTokenError("Token inválido o vencido.") from exc

        if (
            claims.get("token_use") != "access"
            or claims.get("client_id") != settings.COGNITO_CLIENT_ID
        ):
            raise SociosAdminTokenError("Tipo de token no permitido.")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise SociosAdminTokenError("El token no contiene una identidad válida.")
        groups = claims.get("cognito:groups", [])
        if (
            not isinstance(groups, list)
            or settings.COGNITO_SOCIOS_ADMIN_GROUP not in groups
        ):
            raise PermissionError("Acceso exclusivo para administradores de socios.")
        return subject


@lru_cache(maxsize=1)
def get_cognito_socios_admin_jwt_validator() -> CognitoSociosAdminJwtValidator:
    return CognitoSociosAdminJwtValidator()
