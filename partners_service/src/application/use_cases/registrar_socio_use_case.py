from datetime import UTC, datetime

from src.domain.socios.entities import Socio
from src.domain.socios.repositories import SocioRepository


class RegistrarSocioUseCase:
    def __init__(
        self,
        repository: SocioRepository,
        identity_provider=None,
        reloj=lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.identity_provider = identity_provider
        self.reloj = reloj

    async def ejecutar(
        self,
        nombre: str,
        correo: str,
        tipo_socio: str,
        canal_integracion: str,
        actor_id: str,
    ) -> Socio:
        socio, evento = Socio.registrar(
            nombre=nombre,
            correo=correo,
            tipo_socio=tipo_socio,
            canal_integracion=canal_integracion,
            registrado_por=actor_id,
            creado_en=self.reloj(),
        )
        if self.identity_provider is not None:
            await self.identity_provider.invitar(correo)
        await self.repository.registrar(socio, evento)
        return socio
