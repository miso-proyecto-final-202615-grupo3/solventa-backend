from functools import lru_cache

import jwt
from jwt import PyJWKClient

from src.core.config import settings


class ClienteTokenError(Exception):
    pass


class ClienteTokenConfiguracionError(Exception):
    pass


class CognitoClienteJwtValidator:
    def __init__(self) -> None:
        if not settings.COGNITO_REGION or not settings.COGNITO_USER_POOL_ID or not settings.COGNITO_CLIENT_ID:
            raise ClienteTokenConfiguracionError("Cognito no está configurado.")
        self.issuer = f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/{settings.COGNITO_USER_POOL_ID}"
        self.jwks = PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            cache_keys=True,
            lifespan=settings.COGNITO_JWKS_TTL_SECONDS,
        )

    def validar(self, token: str) -> str:
        try:
            key = self.jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=self.issuer, options={"verify_aud": False, "require": ["exp", "iss", "sub"]})
        except jwt.PyJWKClientConnectionError as exc:
            raise ClienteTokenConfiguracionError("No se pudo consultar las claves de Cognito.") from exc
        except jwt.PyJWTError as exc:
            raise ClienteTokenError("Token inválido o vencido.") from exc
        if claims.get("token_use") != "access" or claims.get("client_id") != settings.COGNITO_CLIENT_ID or not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise ClienteTokenError("Token inválido o vencido.")
        return claims["sub"]


@lru_cache(maxsize=1)
def get_cognito_cliente_jwt_validator() -> CognitoClienteJwtValidator:
    return CognitoClienteJwtValidator()
