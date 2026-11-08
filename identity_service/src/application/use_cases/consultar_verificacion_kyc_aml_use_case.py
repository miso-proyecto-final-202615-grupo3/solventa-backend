import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.application.ports.kyc_aml import KycAmlProvider, ProveedorKycAmlError
from src.domain.clientes.entities import ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.clientes.value_objects import EstadoKYC
from src.domain.verificaciones_kyc_aml.entities import EstadoVerificacion, VerificacionKycAml
from src.domain.verificaciones_kyc_aml.repositories import VerificacionKycAmlRepository

logger = logging.getLogger(__name__)

_ESTADO_KYC_CLIENTE = {
    EstadoVerificacion.APROBADA: EstadoKYC.VALIDADO,
    EstadoVerificacion.RECHAZADA: EstadoKYC.RECHAZADO,
}


class VerificacionNoEncontradaError(Exception):
    pass


class VerificacionNoIniciadaError(Exception):
    pass


class ConsultarVerificacionKycAmlUseCase:
    def __init__(
        self,
        clientes: ClienteRepository,
        verificaciones: VerificacionKycAmlRepository,
        proveedor: KycAmlProvider,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
    ) -> None:
        self.clientes = clientes
        self.verificaciones = verificaciones
        self.proveedor = proveedor
        self._commit = commit
        self._rollback = rollback

    async def ejecutar(
        self, cliente_id: uuid.UUID, verificacion_id: uuid.UUID, correlation_id: str
    ) -> VerificacionKycAml:
        verificacion = await self.verificaciones.obtener(cliente_id, verificacion_id)
        if verificacion is None:
            raise VerificacionNoEncontradaError("La verificación indicada no existe.")
        if verificacion.es_final:
            return verificacion
        if (
            verificacion.estado != EstadoVerificacion.INICIADA
            or not verificacion.proveedor_verificacion_id
        ):
            raise VerificacionNoIniciadaError("La verificación no se inició en el proveedor.")

        try:
            resultado = await self.proveedor.consultar_resultado(
                verificacion.proveedor_verificacion_id, correlation_id
            )
        except ProveedorKycAmlError as exc:
            verificacion.registrar_error(exc.codigo, f"[{correlation_id}] {exc.detalle}")
            if await self.verificaciones.actualizar(verificacion):
                await self._commit()
            else:
                await self._rollback()
            raise

        verificacion.aplicar_resultado(resultado, datetime.now(UTC))
        if not await self.verificaciones.actualizar(verificacion):
            # Otro request escribió antes: se conserva lo ya guardado, nunca se sobrescribe.
            await self._rollback()
            actual = await self.verificaciones.obtener(cliente_id, verificacion_id)
            if actual is None:
                raise VerificacionNoEncontradaError("La verificación indicada no existe.")
            return actual

        estado_cliente = _ESTADO_KYC_CLIENTE.get(verificacion.estado)
        if estado_cliente is not None:
            # El cliente se bloquea para que un intento viejo no pise el resultado de uno más reciente.
            cliente = await self.clientes.bloquear_para_actualizar(ClienteId(value=cliente_id))
            ultima = await self.verificaciones.obtener_ultima_id(cliente_id)
            if cliente is not None and ultima == verificacion.id:
                await self.clientes.actualizar_estado_kyc(cliente.id, estado_cliente)
                return verificacion
        await self._commit()
        return verificacion
