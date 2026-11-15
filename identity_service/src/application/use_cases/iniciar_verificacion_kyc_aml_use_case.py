import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from src.application.ports.kyc_aml import KycAmlProvider, ProveedorKycAmlError
from src.application.ports.cotizacion_kyc import CotizacionKycGateway
from src.domain.clientes.entities import ClienteId
from src.domain.clientes.repositories import ClienteRepository
from src.domain.verificaciones_kyc_aml.auditoria import EventoTrazabilidadKycAml
from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    EstadoVerificacion,
    VerificacionKycAml,
    calcular_huella,
    construir_ruta,
)
from src.domain.verificaciones_kyc_aml.repositories import (
    AlmacenamientoDocumentosError,
    DocumentoVerificacionRepository,
    AuditoriaKycAmlRepository,
    VerificacionDuplicadaError,
    VerificacionKycAmlRepository,
)

logger = logging.getLogger(__name__)


class ClienteKycNoEncontradoError(Exception):
    pass


class IdempotencyKeyReutilizadaError(Exception):
    pass


class VerificacionEnProcesoError(Exception):
    pass


class IniciarVerificacionKycAmlUseCase:
    def __init__(
        self,
        clientes: ClienteRepository,
        cotizaciones: CotizacionKycGateway,
        verificaciones: VerificacionKycAmlRepository,
        documentos: DocumentoVerificacionRepository,
        proveedor: KycAmlProvider,
        auditoria: AuditoriaKycAmlRepository,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
        tamano_maximo_documento: int,
    ) -> None:
        self.clientes = clientes
        self.cotizaciones = cotizaciones
        self.verificaciones = verificaciones
        self.documentos = documentos
        self.proveedor = proveedor
        self.auditoria = auditoria
        self._commit = commit
        self._rollback = rollback
        self.tamano_maximo_documento = tamano_maximo_documento

    async def ejecutar(
        self,
        cliente_id: uuid.UUID,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
        idempotency_key: str | None,
        correlation_id: str,
        cotizacion_id: uuid.UUID | None = None,
    ) -> VerificacionKycAml:
        frontal.validar(self.tamano_maximo_documento)
        reverso.validar(self.tamano_maximo_documento)
        if await self.clientes.obtener_por_id(ClienteId(value=cliente_id)) is None:
            raise ClienteKycNoEncontradoError("El cliente indicado no existe.")
        if cotizacion_id is not None:
            await self.cotizaciones.validar_cliente(cotizacion_id, cliente_id, correlation_id)

        huella = calcular_huella(frontal, reverso)
        if idempotency_key:
            existente = await self.verificaciones.obtener_por_idempotency_key(
                cliente_id, idempotency_key
            )
            if existente is not None:
                vinculada = await self.auditoria.cotizacion_de_verificacion(
                    cliente_id, existente.id
                )
                if vinculada is not None and cotizacion_id is not None and vinculada != cotizacion_id:
                    raise IdempotencyKeyReutilizadaError(
                        "La clave de idempotencia ya se usó con otra cotización."
                    )
                return await self._reintentar(
                    existente,
                    huella,
                    frontal,
                    reverso,
                    correlation_id,
                    cotizacion_id if vinculada is None else vinculada,
                )

        verificacion_id = uuid.uuid4()
        verificacion = VerificacionKycAml(
            id=verificacion_id,
            cliente_id=cliente_id,
            proveedor=self.proveedor.nombre,
            huella_documentos=huella,
            ruta_documento_frontal=construir_ruta(
                cliente_id, verificacion_id, f"documento-frontal.{frontal.extension}"
            ),
            ruta_documento_reverso=construir_ruta(
                cliente_id, verificacion_id, f"documento-reverso.{reverso.extension}"
            ),
            iniciada_en=datetime.now(UTC),
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        try:
            await self.verificaciones.crear(verificacion)
            if cotizacion_id is not None:
                await self.auditoria.agregar(
                    self._evento(
                        cotizacion_id,
                        cliente_id,
                        verificacion.id,
                        "KYC_AML_SOLICITADA",
                        "INICIANDO",
                        "identity_service",
                        correlation_id,
                    )
                )
            await self._commit()
        except VerificacionDuplicadaError:
            # Otro request con la misma clave ganó la carrera: se responde con su intento.
            await self._rollback()
            existente = await self.verificaciones.obtener_por_idempotency_key(
                cliente_id, idempotency_key or ""
            )
            if existente is None:
                raise
            return await self._reintentar(
                existente, huella, frontal, reverso, correlation_id, cotizacion_id
            )
        return await self._procesar(verificacion, frontal, reverso, correlation_id)

    async def _reintentar(
        self,
        existente: VerificacionKycAml,
        huella: str,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
        correlation_id: str,
        cotizacion_id: uuid.UUID | None,
    ) -> VerificacionKycAml:
        if existente.huella_documentos != huella:
            raise IdempotencyKeyReutilizadaError(
                "La clave de idempotencia ya se usó con otros documentos."
            )
        if existente.estado == EstadoVerificacion.INICIANDO:
            raise VerificacionEnProcesoError("La verificación se está procesando.")
        if existente.estado != EstadoVerificacion.ERROR:
            return existente

        existente.estado = EstadoVerificacion.INICIANDO
        if not await self.verificaciones.actualizar(existente):
            await self._rollback()
            raise VerificacionEnProcesoError("La verificación se está procesando.")
        if cotizacion_id is not None:
            await self.auditoria.agregar(
                self._evento(
                    cotizacion_id,
                    existente.cliente_id,
                    existente.id,
                    "KYC_AML_REINTENTO",
                    "INICIANDO",
                    "identity_service",
                    correlation_id,
                )
            )
        await self._commit()
        return await self._procesar(existente, frontal, reverso, correlation_id)

    async def _procesar(
        self,
        verificacion: VerificacionKycAml,
        frontal: ArchivoDocumento,
        reverso: ArchivoDocumento,
        correlation_id: str,
    ) -> VerificacionKycAml:
        try:
            rutas = await self.documentos.guardar(
                verificacion.cliente_id, verificacion.id, frontal, reverso
            )
            verificacion.registrar_documentos(rutas)
            inicio = await self.proveedor.iniciar_verificacion(
                verificacion.cliente_id, verificacion.id, rutas, frontal, reverso, correlation_id
            )
        except AlmacenamientoDocumentosError as exc:
            await self._registrar_fallo(verificacion, "ALMACENAMIENTO_NO_DISPONIBLE", str(exc))
            raise
        except ProveedorKycAmlError as exc:
            await self._registrar_fallo(verificacion, exc.codigo, exc.detalle)
            raise
        except Exception as exc:
            logger.exception("Falló el inicio de la verificación KYC/AML.")
            await self._registrar_fallo(verificacion, "ERROR_INESPERADO", type(exc).__name__)
            raise

        verificacion.marcar_iniciada(inicio)
        if not await self.verificaciones.actualizar(verificacion):
            await self._rollback()
            raise VerificacionEnProcesoError("La verificación fue modificada concurrentemente.")
        cotizacion_id = await self.auditoria.cotizacion_de_verificacion(
            verificacion.cliente_id, verificacion.id
        )
        if cotizacion_id is not None:
            await self.auditoria.agregar(
                self._evento(
                    cotizacion_id,
                    verificacion.cliente_id,
                    verificacion.id,
                    "KYC_AML_INICIADA",
                    "INICIADA",
                    verificacion.proveedor,
                    correlation_id,
                    detalles={"proveedor": verificacion.proveedor},
                )
            )
        await self._commit()
        return verificacion

    async def _registrar_fallo(
        self, verificacion: VerificacionKycAml, codigo: str, detalle: str
    ) -> None:
        verificacion.estado = EstadoVerificacion.ERROR
        verificacion.registrar_error(codigo, f"[{verificacion.correlation_id}] {detalle}")
        if await self.verificaciones.actualizar(verificacion):
            cotizacion_id = await self.auditoria.cotizacion_de_verificacion(
                verificacion.cliente_id, verificacion.id
            )
            if cotizacion_id is not None:
                await self.auditoria.agregar(
                    self._evento(
                        cotizacion_id,
                        verificacion.cliente_id,
                        verificacion.id,
                        "KYC_AML_ERROR",
                        codigo,
                        "identity_service",
                        verificacion.correlation_id,
                        detalles={"codigo": codigo},
                    )
                )
            await self._commit()
        else:
            await self._rollback()

    @staticmethod
    def _evento(
        cotizacion_id: uuid.UUID,
        cliente_id: uuid.UUID,
        verificacion_id: uuid.UUID,
        tipo: str,
        resultado: str,
        origen: str,
        correlation_id: str,
        *,
        actor_id: str | None = None,
        detalles: dict | None = None,
    ) -> EventoTrazabilidadKycAml:
        return EventoTrazabilidadKycAml(
            cotizacion_id=cotizacion_id,
            cliente_id=cliente_id,
            tipo=tipo,
            ocurrido_en=datetime.now(UTC),
            origen=origen,
            actor_id=actor_id,
            resultado=resultado,
            referencia_id=str(verificacion_id),
            correlation_id=correlation_id,
            detalles=detalles or {},
        )
