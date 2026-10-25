import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.application.ports.consentimiento_biometrico import ConsentimientoBiometricoPort
from src.application.ports.liveness import (
    LivenessAdapterUnavailableError,
    LivenessSessionInfo,
    LivenessVerificationPort,
)
from src.domain.activacion_movil.entities import (
    DatosDispositivo,
    EstadoSesion,
    SesionActivacion,
)
from src.domain.activacion_movil.politica_intentos import PoliticaIntentos
from src.domain.activacion_movil.repositories import ActivacionMovilRepository
from src.domain.clientes.repositories import ClienteRepository

logger = logging.getLogger(__name__)


class ClienteNoRegistradoError(Exception):
    pass


class ConsentimientoBiometricoRequeridoError(Exception):
    pass


class IntentosAgotadosError(Exception):
    pass


@dataclass(frozen=True)
class InicioActivacionResultado:
    dispositivo_vinculado: bool
    sesion_id: str | None = None
    expira_en: datetime | None = None
    captura: dict | None = None
    intentos_restantes: int | None = None


class IniciarActivacionMovilUseCase:
    def __init__(
        self,
        clientes: ClienteRepository,
        activaciones: ActivacionMovilRepository,
        consentimiento: ConsentimientoBiometricoPort,
        liveness: LivenessVerificationPort,
        commit: Callable[[], Awaitable[None]],
        politica: PoliticaIntentos | None = None,
        ahora: Callable[[], datetime] | None = None,
        margen_verificacion: timedelta = timedelta(seconds=15),
    ) -> None:
        self._clientes = clientes
        self._activaciones = activaciones
        self._consentimiento = consentimiento
        self._liveness = liveness
        self._commit = commit
        self._politica = politica or PoliticaIntentos()
        self._ahora = ahora or (lambda: datetime.now(UTC))
        self._margen_verificacion = margen_verificacion

    async def ejecutar(
        self,
        correo: str,
        dispositivo: DatosDispositivo,
        correlation_id: str,
    ) -> InicioActivacionResultado:
        cliente = await self._clientes.obtener_por_correo(correo)
        if cliente is None:
            raise ClienteNoRegistradoError()

        if await self._activaciones.dispositivo_esta_vinculado(
            cliente.id.value, dispositivo.installation_id
        ):
            return InicioActivacionResultado(dispositivo_vinculado=True)

        if not await self._consentimiento.otorgado(cliente.id.value):
            raise ConsentimientoBiometricoRequeridoError()

        cliente_bloqueado = await self._clientes.bloquear_para_actualizar(cliente.id)
        if cliente_bloqueado is None:
            raise ClienteNoRegistradoError()

        ahora = self._ahora()
        await self._activaciones.anular_intentos_en_curso_vencidos(
            cliente.id.value,
            ahora - self._margen_verificacion,
            ahora,
        )
        consumidos = await self._activaciones.contar_intentos_consumidos(
            cliente.id.value, ahora - self._politica.ventana
        )
        if self._politica.bloqueado(consumidos):
            raise IntentosAgotadosError()

        anterior = await self._activaciones.obtener_sesion_creada(
            dispositivo.installation_id
        )
        if anterior is not None:
            await self._activaciones.cancelar_sesion(anterior.id)
            await self._commit()
            try:
                await self._liveness.cancel_session(anterior.id, correlation_id)
            except LivenessAdapterUnavailableError:
                logger.warning(
                    "No se pudo cancelar el reto remoto ya invalidado",
                    extra={"sesion_id": anterior.id, "correlation_id": correlation_id},
                )

        info = await self._liveness.start_session(
            str(cliente.id.value), correlation_id
        )
        sesion = self._crear_sesion(cliente.id.value, dispositivo, info, ahora)
        await self._activaciones.guardar_sesion(sesion)
        await self._commit()
        return InicioActivacionResultado(
            dispositivo_vinculado=False,
            sesion_id=sesion.id,
            expira_en=sesion.expira_en,
            captura=info.capture,
            intentos_restantes=self._politica.intentos_restantes(consumidos),
        )

    @staticmethod
    def _crear_sesion(
        cliente_id, dispositivo: DatosDispositivo, info: LivenessSessionInfo, creada_en: datetime
    ) -> SesionActivacion:
        try:
            expira_en = datetime.fromisoformat(info.expires_at.replace("Z", "+00:00"))
            tipo_captura = info.capture.get("type", info.capture.get("kind"))
        except (AttributeError, ValueError) as exc:
            raise LivenessAdapterUnavailableError() from exc
        if not isinstance(tipo_captura, str):
            raise LivenessAdapterUnavailableError()
        return SesionActivacion(
            id=info.session_id,
            cliente_id=cliente_id,
            dispositivo=dispositivo,
            tipo_captura=tipo_captura,
            estado=EstadoSesion.CREADA,
            creada_en=creada_en,
            expira_en=expira_en,
        )
