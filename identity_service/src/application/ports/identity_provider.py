from abc import ABC, abstractmethod


class IdentityProvider(ABC):
    @abstractmethod
    async def registrar_usuario(self, correo: str, password: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def eliminar_usuario(self, correo: str) -> None:
        raise NotImplementedError