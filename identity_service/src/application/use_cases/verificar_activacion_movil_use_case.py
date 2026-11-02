import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from src.application.ports.liveness import (
    LivenessAdapterUnavailableError,
    LivenessInvalidCaptureError,
    LivenessSessionCancelledError,
    LivenessSessionConflictError,
    LivenessSessionNotFoundError,
    LivenessVerificationPort,
)
from src.domain.activacion_movil.entities import EstadoIntento, EstadoSesion, IntentoPruebaVida
from src.domain.activacion_movil.politica_intentos import PoliticaIntentos
from src.domain.activacion_movil.repositories import ActivacionMovilRepository
from src.domain.clientes.repositories import ClienteRepository

logger = logging.getLogger(__name__)


class SesionActivacionInvalidaError(Exception):
    pass


class SesionActivacionCanceladaError(Exception):
    pass


class CapturaActivacionInvalidaError(Exception):
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
    """TX1 reserva el intento; el adaptador decide fuera de la transacción; TX2 cierra y vincula."""

    def __init__(
        self,
        clientes: ClienteRepository,
        activaciones: ActivacionMovilRepository,
        liveness: LivenessVerificationPort,
        commit: Callable[[], Awaitable[None]],
        politica: PoliticaIntentos | None = None,
        ahora: Callable[[], datetime] | None = None,
        margen_verificacion: timedelta = timedelta(seconds=15),
        rollback: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._clientes, self._activaciones, self._liveness = clientes, activaciones, liveness
        self._commit = commit
        self._rollback = rollback
        self._politica = politica or PoliticaIntentos()
        self._ahora = ahora or (lambda: datetime.now(UTC))
        self._margen_verificacion = margen_verificacion

    async def ejecutar(
        self,
        correo: str,
        sesion_id: str,
        nonce: str | None,
        frames: dict[str, bytes],
        captured_at: dict[str, str],
        correlation_id: str,
        sdk_result: str | None = None,
    ) -> VerificacionActivacionResultado:
        cliente = await self._clientes.obtener_por_correo(correo)
        if cliente is None:
            raise SesionActivacionInvalidaError()

        # TX1: serializa por cliente, recupera intentos colgados (D12) y reserva el intento.
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
        intento = IntentoPruebaVida(
            uuid4(), cliente.id.value, sesion.id, sesion.dispositivo.installation_id,
            EstadoIntento.EN_CURSO, ahora,
        )
        await self._activaciones.guardar_intento(intento)
        await self._activaciones.actualizar_estado_sesion(sesion.id, EstadoSesion.EN_VERIFICACION)
        await self._commit()

        try:
            resultado = await self._liveness.verify(
                sesion.id, str(cliente.id.value), nonce, frames, captured_at, correlation_id,
                sdk_result=sdk_result,
            )
        except LivenessAdapterUnavailableError as exc:
            # FRAMES: el reto no se reenvía (D11). SDK: la decisión del proveedor puede llegar después.
            estado = EstadoSesion.CANCELADA if sesion.tipo_captura == "FRAMES" else EstadoSesion.CREADA
            await self._anular(intento.id, sesion.id, estado, "PROVEEDOR_NO_DISPONIBLE")
            raise VerificacionPruebaVidaNoDisponibleError() from exc
        except LivenessInvalidCaptureError as exc:
            # La evidencia no se pudo evaluar (formato, tamaño o tiempos): no cuenta como intento (D11).
            await self._anular(intento.id, sesion.id, EstadoSesion.CANCELADA, "CAPTURA_INVALIDA")
            raise CapturaActivacionInvalidaError() from exc
        except LivenessSessionCancelledError as exc:
            await self._anular(intento.id, sesion.id, EstadoSesion.CANCELADA, "CANCELADA_POR_USUARIO")
            raise SesionActivacionCanceladaError() from exc
        except (LivenessSessionConflictError, LivenessSessionNotFoundError) as exc:
            await self._anular(intento.id, sesion.id, EstadoSesion.CANCELADA, "SESION_INVALIDA")
            raise SesionActivacionInvalidaError() from exc

        # TX2: cierra el intento y, si aprobó, revoca vínculos previos y vincula (D2).
        estado = EstadoIntento.APROBADO if resultado.approved else EstadoIntento.RECHAZADO
        resuelto_en = self._ahora()
        try:
            await self._activaciones.actualizar_estado_intento(
                intento.id, estado, resuelto_en, resultado.verification_id, resultado.reason
            )
            await self._activaciones.actualizar_estado_sesion(sesion.id, EstadoSesion.USADA)
            if resultado.approved:
                await self._activaciones.vincular_dispositivo(
                    cliente.id.value, sesion.dispositivo, resultado.verification_id, resuelto_en
                )
            await self._commit()
        except IntegrityError as exc:
            # Los índices únicos parciales detectaron un vínculo activo concurrente.
            if self._rollback is not None:
                await self._rollback()
            logger.error(
                "activacion_movil_conflicto_vinculo",
                extra={"sesion_id": sesion.id, "correlation_id": correlation_id},
            )
            await self._anular(intento.id, sesion.id, EstadoSesion.CANCELADA, "CONFLICTO_VINCULO")
            raise VerificacionPruebaVidaNoDisponibleError() from exc

        logger.info(
            "activacion_movil_verificada",
            extra={
                "sesion_id": sesion.id, "estado": estado.value, "folio": resultado.verification_id,
                "motivo": resultado.reason, "correlation_id": correlation_id,
            },
        )
        # Un aprobado no consume cupo; un rechazo sí.
        consumidos_final = consumidos if resultado.approved else consumidos + 1
        return VerificacionActivacionResultado(
            resultado="APROBADO" if resultado.approved else "RECHAZADO",
            folio=resultado.verification_id,
            intento=consumidos + 1,
            intentos_restantes=self._politica.intentos_restantes(consumidos_final),
            dispositivo_vinculado=resultado.approved,
            vinculado_en=resuelto_en if resultado.approved else None,
            motivo=resultado.reason,
        )

    async def _anular(self, intento_id, sesion_id: str, estado_sesion: EstadoSesion, motivo: str) -> None:
        await self._activaciones.actualizar_estado_intento(
            intento_id, EstadoIntento.ANULADO, self._ahora(), motivo=motivo
        )
        await self._activaciones.actualizar_estado_sesion(sesion_id, estado_sesion)
        await self._commit()
