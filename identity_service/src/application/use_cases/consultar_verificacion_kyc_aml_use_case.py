import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.application.ports.kyc_aml import KycAmlProvider, ProveedorKycAmlError
from src.domain.clientes.entities import ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.clientes.value_objects import EstadoKYC
from src.domain.verificaciones_kyc_aml.auditoria import EventoTrazabilidadKycAml
from src.domain.verificaciones_kyc_aml.entities import EstadoVerificacion, VerificacionKycAml
from src.domain.verificaciones_kyc_aml.repositories import (
    AuditoriaKycAmlRepository,
    VerificacionKycAmlRepository,
)

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
        auditoria: AuditoriaKycAmlRepository,
        proveedor: KycAmlProvider,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
    ) -> None:
        self.clientes = clientes
        self.verificaciones = verificaciones
        self.auditoria = auditoria
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
                await self._registrar_evento(
                    verificacion,
                    "KYC_AML_ERROR",
                    exc.codigo,
                    correlation_id,
                    {"codigo": exc.codigo},
                )
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

        if verificacion.resultado_kyc is not None or verificacion.resultado_aml is not None:
            await self._registrar_evento(
                verificacion,
                "KYC_AML_RESULTADO",
                verificacion.estado.value if verificacion.es_final else "PENDIENTE",
                correlation_id,
                {
                    "kyc": verificacion.resultado_kyc.value
                    if verificacion.resultado_kyc
                    else "PENDIENTE",
                    "aml": verificacion.resultado_aml.value
                    if verificacion.resultado_aml
                    else "PENDIENTE",
                },
            )

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

    async def _registrar_evento(
        self,
        verificacion: VerificacionKycAml,
        tipo: str,
        resultado: str,
        correlation_id: str,
        detalles: dict[str, str],
    ) -> None:
        cotizacion_id = await self.auditoria.cotizacion_de_verificacion(
            verificacion.cliente_id, verificacion.id
        )
        if cotizacion_id is None:
            return
        ultimo = await self.auditoria.ultimo_evento_verificacion(
            verificacion.cliente_id, verificacion.id, tipo
        )
        if ultimo is not None and ultimo.resultado == resultado and ultimo.detalles == detalles:
            return
        await self.auditoria.agregar(
            EventoTrazabilidadKycAml(
                cotizacion_id=cotizacion_id,
                cliente_id=verificacion.cliente_id,
                tipo=tipo,
                ocurrido_en=datetime.now(UTC),
                origen=verificacion.proveedor,
                resultado=resultado,
                referencia_id=str(verificacion.id),
                correlation_id=correlation_id,
                detalles=detalles,
            )
        )
