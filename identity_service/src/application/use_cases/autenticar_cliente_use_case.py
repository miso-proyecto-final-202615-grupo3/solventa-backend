from src.application.ports.identity_provider import (
    AutenticarResult,
    IdentityProvider,
)
from src.presentation.schemas import PasswordVerify


class AutenticarClienteUseCase:
    def __init__(self, identity_provider: IdentityProvider) -> None:
        self.identity_provider = identity_provider

    async def ejecutar(self, command: PasswordVerify) -> AutenticarResult:
        return await self.identity_provider.autenticar_usuario(
            str(command.correo), command.password
        )