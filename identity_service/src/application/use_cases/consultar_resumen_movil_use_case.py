import uuid
from dataclasses import dataclass

from src.domain.activacion_movil.repositories import ActivacionMovilRepository
from src.domain.clientes.repositories import ClienteRepository


class ResumenClienteNoEncontradoError(Exception):
    pass


@dataclass(frozen=True)
class ResumenMovil:
    id: uuid.UUID
    nombre: str
    estado_kyc: str
    dispositivo_vinculado: bool


class ConsultarResumenMovilUseCase:
    """Datos del cliente que el BFF Móvil agrega al login; no expone la evidencia biométrica."""

    def __init__(self, clientes: ClienteRepository, activaciones: ActivacionMovilRepository) -> None:
        self._clientes = clientes
        self._activaciones = activaciones

    async def ejecutar(self, correo: str, installation_id: uuid.UUID | None) -> ResumenMovil:
        cliente = await self._clientes.obtener_por_correo(correo)
        if cliente is None:
            raise ResumenClienteNoEncontradoError()
        vinculado = installation_id is not None and await self._activaciones.dispositivo_esta_vinculado(
            cliente.id.value, installation_id
        )
        return ResumenMovil(
            id=cliente.id.value,
            nombre=f"{cliente.nombres} {cliente.apellidos}".strip(),
            estado_kyc=cliente.estado_kyc.value,
            dispositivo_vinculado=vinculado,
        )
