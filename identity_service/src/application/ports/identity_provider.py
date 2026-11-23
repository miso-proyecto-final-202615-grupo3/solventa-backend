from abc import ABC, abstractmethod
from dataclasses import dataclass


class IdentityProviderError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class PasswordRecoveryCodeError(Exception):
    pass


class PasswordRecoveryPasswordError(Exception):
    pass


class PasswordRecoveryRateLimitError(Exception):
    pass


@dataclass(frozen=True)
class AutenticarResult:
    access_token: str
    id_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str = "Bearer"


class IdentityProvider(ABC):
    async def registrar_prospecto(self, correo: str, password: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def registrar_usuario(self, correo: str, password: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def autenticar_usuario(
        self, correo: str, password: str
    ) -> AutenticarResult:
        raise NotImplementedError

    @abstractmethod
    async def renovar_sesion(self, refresh_token: str) -> AutenticarResult:
        raise NotImplementedError

    @abstractmethod
    async def eliminar_usuario(self, correo: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def solicitar_recuperacion_clave(self, correo: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def confirmar_recuperacion_clave(
        self, correo: str, codigo: str, nueva_clave: str
    ) -> None:
        raise NotImplementedError
