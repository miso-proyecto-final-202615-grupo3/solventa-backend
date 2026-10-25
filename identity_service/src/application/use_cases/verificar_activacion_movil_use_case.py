from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from src.application.ports.liveness import LivenessVerificationPort
from src.domain.activacion_movil.entities import EstadoIntento, EstadoSesion, IntentoPruebaVida
from src.domain.activacion_movil.repositories import ActivacionMovilRepository
from src.domain.clientes.repositories import ClienteRepository


class SesionActivacionInvalidaError(Exception):
    pass


@dataclass(frozen=True)
class VerificacionActivacionResultado:
    aprobada: bool
    folio: str | None
    motivo: str | None


class VerificarActivacionMovilUseCase:
    def __init__(self, clientes: ClienteRepository, activaciones: ActivacionMovilRepository,
                 liveness: LivenessVerificationPort, commit: Callable[[], Awaitable[None]], ahora=None) -> None:
        self._clientes, self._activaciones, self._liveness, self._commit = clientes, activaciones, liveness, commit
        self._ahora = ahora or (lambda: datetime.now(UTC))

    async def ejecutar(self, correo: str, sesion_id: str, nonce: str, frames: dict[str, bytes], correlation_id: str) -> VerificacionActivacionResultado:
        cliente = await self._clientes.obtener_por_correo(correo)
        if cliente is None:
            raise SesionActivacionInvalidaError()
        await self._clientes.bloquear_para_actualizar(cliente.id)
        sesion = await self._activaciones.obtener_sesion(cliente.id.value, sesion_id)
        ahora = self._ahora()
        if sesion is None or sesion.estado != EstadoSesion.CREADA or sesion.expira_en <= ahora:
            raise SesionActivacionInvalidaError()
        intento = IntentoPruebaVida(uuid4(), cliente.id.value, sesion.id, sesion.dispositivo.installation_id, EstadoIntento.EN_CURSO, ahora)
        await self._activaciones.guardar_intento(intento)
        await self._activaciones.actualizar_estado_sesion(sesion.id, EstadoSesion.EN_VERIFICACION)
        await self._commit()
        resultado = await self._liveness.verify(sesion.id, str(cliente.id.value), nonce, frames, correlation_id)
        estado = EstadoIntento.APROBADO if resultado.approved else EstadoIntento.RECHAZADO
        await self._activaciones.actualizar_estado_intento(intento.id, estado, self._ahora(), resultado.verification_id, resultado.reason)
        await self._activaciones.actualizar_estado_sesion(sesion.id, EstadoSesion.USADA)
        if resultado.approved:
            await self._activaciones.vincular_dispositivo(cliente.id.value, sesion.dispositivo, resultado.verification_id, self._ahora())
        await self._commit()
        return VerificacionActivacionResultado(resultado.approved, resultado.verification_id if resultado.approved else None, resultado.reason)
