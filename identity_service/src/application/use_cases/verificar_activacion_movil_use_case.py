from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from src.application.ports.liveness import LivenessAdapterUnavailableError, LivenessVerificationPort
from src.domain.activacion_movil.entities import EstadoIntento, EstadoSesion, IntentoPruebaVida
from src.domain.activacion_movil.politica_intentos import PoliticaIntentos
from src.domain.activacion_movil.repositories import ActivacionMovilRepository
from src.domain.clientes.repositories import ClienteRepository


class SesionActivacionInvalidaError(Exception):
    pass


class IntentosActivacionAgotadosError(Exception):
    pass


class VerificacionPruebaVidaNoDisponibleError(Exception):
    pass


@dataclass(frozen=True)
class VerificacionActivacionResultado:
    resultado: str
    folio: str | None
    intento: int
    intentos_restantes: int
    dispositivo_vinculado: bool
    vinculado_en: datetime | None
    motivo: str | None


class VerificarActivacionMovilUseCase:
    def __init__(self, clientes: ClienteRepository, activaciones: ActivacionMovilRepository,
                 liveness: LivenessVerificationPort, commit: Callable[[], Awaitable[None]],
                 politica: PoliticaIntentos | None = None, ahora=None,
                 margen_verificacion: timedelta = timedelta(seconds=15)) -> None:
        self._clientes, self._activaciones, self._liveness, self._commit = clientes, activaciones, liveness, commit
        self._politica = politica or PoliticaIntentos()
        self._ahora = ahora or (lambda: datetime.now(UTC))
        self._margen_verificacion = margen_verificacion

    async def ejecutar(self, correo: str, sesion_id: str, nonce: str, frames: dict[str, bytes], captured_at: dict[str, str], correlation_id: str) -> VerificacionActivacionResultado:
        cliente = await self._clientes.obtener_por_correo(correo)
        if cliente is None:
            raise SesionActivacionInvalidaError()
        await self._clientes.bloquear_para_actualizar(cliente.id)
        ahora = self._ahora()
        await self._activaciones.anular_intentos_en_curso_vencidos(
            cliente.id.value, ahora - self._margen_verificacion, ahora
        )
        consumidos = await self._activaciones.contar_intentos_consumidos(
            cliente.id.value, ahora - self._politica.ventana
        )
        if self._politica.bloqueado(consumidos):
            raise IntentosActivacionAgotadosError()
        sesion = await self._activaciones.obtener_sesion(cliente.id.value, sesion_id)
        if sesion is None or sesion.estado != EstadoSesion.CREADA or sesion.expira_en <= ahora:
            raise SesionActivacionInvalidaError()
        intento = IntentoPruebaVida(uuid4(), cliente.id.value, sesion.id, sesion.dispositivo.installation_id, EstadoIntento.EN_CURSO, ahora)
        await self._activaciones.guardar_intento(intento)
        await self._activaciones.actualizar_estado_sesion(sesion.id, EstadoSesion.EN_VERIFICACION)
        await self._commit()
        try:
            resultado = await self._liveness.verify(sesion.id, str(cliente.id.value), nonce, frames, captured_at, correlation_id)
        except LivenessAdapterUnavailableError as exc:
            await self._activaciones.actualizar_estado_intento(
                intento.id, EstadoIntento.ANULADO, self._ahora(), motivo="PROVEEDOR_NO_DISPONIBLE"
            )
            await self._activaciones.actualizar_estado_sesion(sesion.id, EstadoSesion.CANCELADA)
            await self._commit()
            raise VerificacionPruebaVidaNoDisponibleError() from exc
        estado = EstadoIntento.APROBADO if resultado.approved else EstadoIntento.RECHAZADO
        resuelto_en = self._ahora()
        await self._activaciones.actualizar_estado_intento(intento.id, estado, resuelto_en, resultado.verification_id, resultado.reason)
        await self._activaciones.actualizar_estado_sesion(sesion.id, EstadoSesion.USADA)
        if resultado.approved:
            await self._activaciones.vincular_dispositivo(cliente.id.value, sesion.dispositivo, resultado.verification_id, self._ahora())
        await self._commit()
        return VerificacionActivacionResultado(
            resultado="APROBADO" if resultado.approved else "RECHAZADO",
            folio=resultado.verification_id if resultado.approved else None,
            intento=consumidos + 1,
            intentos_restantes=self._politica.intentos_restantes(consumidos + 1),
            dispositivo_vinculado=resultado.approved,
            vinculado_en=resuelto_en if resultado.approved else None,
            motivo=resultado.reason,
        )
