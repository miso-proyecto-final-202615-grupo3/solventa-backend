from src.application.ports.identity_provider import IdentityProvider


class RecuperarClaveUseCase:
    def __init__(self, identity_provider: IdentityProvider) -> None:
        self.identity_provider = identity_provider

    async def solicitar(self, correo: str) -> None:
        await self.identity_provider.solicitar_recuperacion_clave(correo)

    async def confirmar(self, correo: str, codigo: str, nueva_clave: str) -> None:
        await self.identity_provider.confirmar_recuperacion_clave(
            correo, codigo, nueva_clave
        )
