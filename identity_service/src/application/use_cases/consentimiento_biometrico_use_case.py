import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from src.domain.clientes.repositories import ClienteRepository
from src.domain.consentimiento_biometrico.entities import (
    DecisionBiometrica,
    DecisionConsentimientoBiometrico,
    EstadoConsentimientoBiometrico,
)
from src.domain.consentimiento_biometrico.repositories import ConsentimientoBiometricoRepository

logger = logging.getLogger(__name__)


class ClienteConsentimientoNoEncontradoError(Exception):
    pass


class VersionTerminosDesactualizadaError(Exception):
    pass


class FechaDecisionInvalidaError(Exception):
    pass


class GestionarConsentimientoBiometricoUseCase:
    """Consulta y registra el consentimiento biométrico del cliente (HU3.1.3).

    Cada decisión (aceptación o rechazo) se guarda con la fecha en que la tomó el cliente, la fecha
    de registro en el servidor, la versión del texto legal y la instalación: es el registro auditable.
    """

    # Tolerancia al reloj del dispositivo y antigüedad máxima de una decisión pendiente de enviar.
    DESFASE_MAXIMO = timedelta(minutes=5)
    ANTIGUEDAD_MAXIMA = timedelta(hours=24)

    def __init__(
        self,
        clientes: ClienteRepository,
        consentimientos: ConsentimientoBiometricoRepository,
        version_vigente: str,
        commit: Callable[[], Awaitable[None]],
        ahora: Callable[[], datetime] | None = None,
    ) -> None:
        self._clientes = clientes
        self._consentimientos = consentimientos
        self._version_vigente = version_vigente
        self._commit = commit
        self._ahora = ahora or (lambda: datetime.now(UTC))

    async def consultar(self, correo: str) -> EstadoConsentimientoBiometrico:
        cliente_id = await self._cliente_id(correo)
        ultima = await self._consentimientos.ultima_decision(cliente_id)
        return EstadoConsentimientoBiometrico.desde(ultima, self._version_vigente)

    async def registrar(
        self,
        correo: str,
        decision: DecisionBiometrica,
        version_terminos: str,
        installation_id: uuid.UUID,
        decidido_en: datetime,
        correlation_id: str,
    ) -> DecisionConsentimientoBiometrico:
        cliente_id = await self._cliente_id(correo)
        if version_terminos != self._version_vigente:
            raise VersionTerminosDesactualizadaError()
        ahora = self._ahora()
        if decidido_en.tzinfo is None or not (
            ahora - self.ANTIGUEDAD_MAXIMA <= decidido_en <= ahora + self.DESFASE_MAXIMO
        ):
            raise FechaDecisionInvalidaError()

        registro = DecisionConsentimientoBiometrico(
            cliente_id=cliente_id,
            decision=decision,
            version_terminos=version_terminos,
            installation_id=installation_id,
            decidido_en=decidido_en,
            registrado_en=ahora,
        )
        await self._consentimientos.registrar(registro)
        await self._commit()
        logger.info(
            "biometric_consent decision=%s version=%s correlation_id=%s",
            decision.value, version_terminos, correlation_id,
        )
        return registro

    async def _cliente_id(self, correo: str) -> uuid.UUID:
        cliente = await self._clientes.obtener_por_correo(correo)
        if cliente is None:
            raise ClienteConsentimientoNoEncontradoError()
        return cliente.id.value
