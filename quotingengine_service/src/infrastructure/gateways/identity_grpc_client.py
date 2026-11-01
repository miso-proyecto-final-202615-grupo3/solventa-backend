import asyncio
import logging
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

import grpc

from src.application.ports.perfil_cliente_gateway import (
    ClienteNoEncontradoError,
    ConsentimientoNoOtorgadoError,
    PerfilCliente,
    PerfilClienteGateway,
    PerfilNoDisponibleError,
)
from src.core.config import settings
from src.infrastructure.grpc_generated import (
    identity_profile_pb2,
    identity_profile_pb2_grpc,
)
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class IdentityGrpcClient(PerfilClienteGateway):
    """Obtiene el perfil del cliente de identity_service vía gRPC.

    Disponibilidad (DIS-2 / ESC-001): timeout, circuit breaker y bulkhead.
    Cualquier falla de infraestructura se normaliza a PerfilNoDisponibleError
    para que el motor continúe con degradación controlada.
    """

    def __init__(
        self,
        address: str | None = None,
        timeout: float | None = None,
        max_concurrency: int | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        channel: grpc.aio.Channel | None = None,
    ) -> None:
        self.timeout = timeout if timeout is not None else settings.IDENTITY_GRPC_TIMEOUT_SECONDS
        self._channel = channel or grpc.aio.insecure_channel(
            address or settings.IDENTITY_GRPC_ADDRESS
        )
        self._stub = identity_profile_pb2_grpc.IdentityProfileStub(self._channel)
        self._bulkhead = asyncio.Semaphore(
            max_concurrency or settings.IDENTITY_GRPC_MAX_CONCURRENCY
        )
        self._breaker = circuit_breaker or CircuitBreaker(
            settings.IDENTITY_CB_FAILURE_THRESHOLD,
            settings.IDENTITY_CB_RECOVERY_SECONDS,
        )

    async def cerrar(self) -> None:
        await self._channel.close()

    async def obtener_perfil(self, cliente_id: uuid.UUID) -> PerfilCliente:
        if self._bulkhead.locked():
            raise PerfilNoDisponibleError("bulkhead saturado")
        if not self._breaker.permitir():
            raise PerfilNoDisponibleError("circuito abierto")

        async with self._bulkhead:
            try:
                respuesta = await self._stub.ObtenerPerfilCliente(
                    identity_profile_pb2.ObtenerPerfilClienteRequest(
                        cliente_id=str(cliente_id)
                    ),
                    timeout=self.timeout,
                )
            except grpc.aio.AioRpcError as exc:
                return self._manejar_error(exc)
            except Exception as exc:
                self._breaker.registrar_falla()
                logger.warning("Falla inesperada consultando identidad", exc_info=True)
                raise PerfilNoDisponibleError(str(exc)) from exc

        self._breaker.registrar_exito()
        return _a_perfil(respuesta)

    def _manejar_error(self, exc: grpc.aio.AioRpcError):
        codigo = exc.code()
        # errores de negocio: el servicio respondió, el circuito no se afecta
        if codigo == grpc.StatusCode.NOT_FOUND:
            self._breaker.registrar_exito()
            raise ClienteNoEncontradoError(exc.details()) from exc
        if codigo == grpc.StatusCode.PERMISSION_DENIED:
            self._breaker.registrar_exito()
            raise ConsentimientoNoOtorgadoError(exc.details()) from exc
        self._breaker.registrar_falla()
        logger.warning("Identidad no disponible (%s)", codigo)
        raise PerfilNoDisponibleError(str(codigo)) from exc


def _a_perfil(r: identity_profile_pb2.PerfilClienteResponse) -> PerfilCliente:
    try:
        fecha = date.fromisoformat(r.fecha_nacimiento) if r.fecha_nacimiento else None
    except ValueError:
        fecha = None
    return PerfilCliente(
        cliente_id=uuid.UUID(r.id),
        nombres=r.nombres,
        apellidos=r.apellidos,
        tipo_documento=r.tipo_documento,
        numero_identificacion=r.numero_identificacion,
        correo=r.correo,
        fecha_nacimiento=fecha,
        pais_residencia=r.pais_residencia,
        telefono=r.telefono,
        estado_kyc=r.estado_kyc,
        open_finance_disponible=r.open_finance_disponible,
        ingreso_mensual=_decimal_or_none(r.ingreso_mensual),
        ahorros_liquidos=_decimal_or_none(r.ahorros_liquidos),
        dti_pct=_decimal_or_none(r.dti_pct),
        sobregiros_12_meses=(
            r.sobregiros_12_meses if r.open_finance_disponible else None
        ),
        score=r.score if r.open_finance_disponible else None,
    )


def _decimal_or_none(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None
