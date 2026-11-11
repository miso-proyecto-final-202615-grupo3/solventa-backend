import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from src.domain.firmas.entities import (
    ArchivoFirma,
    EstadoFirma,
    FirmaDigital,
    calcular_fingerprint,
    construir_ruta,
)
from src.domain.firmas.repositories import (
    AlmacenamientoFirmaRepository,
    FirmaDigitalRepository,
    FirmaDuplicadaError,
)

logger = logging.getLogger(__name__)


class IdempotencyKeyReutilizadaError(Exception):
    pass


class FirmaYaVinculadaError(Exception):
    pass


class FirmaConcurrenteError(Exception):
    pass


@dataclass(frozen=True)
class ResultadoCaptura:
    firma: FirmaDigital
    creada: bool


class CapturarFirmaDigitalUseCase:
    def __init__(
        self,
        firmas: FirmaDigitalRepository,
        almacenamiento: AlmacenamientoFirmaRepository,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
        tamano_maximo: int,
        proveedor_firma: str,
    ) -> None:
        self.firmas = firmas
        self.almacenamiento = almacenamiento
        self._commit = commit
        self._rollback = rollback
        self.tamano_maximo = tamano_maximo
        self.proveedor_firma = proveedor_firma

    async def ejecutar(
        self,
        cliente_id: uuid.UUID,
        cotizacion_id: uuid.UUID,
        producto_id: uuid.UUID,
        archivo: ArchivoFirma,
        idempotency_key: str,
        correlation_id: str,
    ) -> ResultadoCaptura:
        archivo.validar(self.tamano_maximo)
        firma_hash = archivo.hash

        existente = await self.firmas.obtener_por_idempotency_key(cliente_id, idempotency_key)
        if existente is not None:
            return self._repetir(existente, firma_hash, cotizacion_id, producto_id)

        activa = await self.firmas.obtener_activa_por_cotizacion(cotizacion_id)
        if activa is not None and activa.estado == EstadoFirma.VINCULADA:
            raise FirmaYaVinculadaError("La cotización ya tiene una póliza asociada a su firma.")

        firma_id = uuid.uuid4()
        capturada_en = datetime.now(UTC)
        firma = FirmaDigital(
            firma_id=firma_id,
            cliente_id=cliente_id,
            cotizacion_id=cotizacion_id,
            producto_id=producto_id,
            proveedor_firma=self.proveedor_firma,
            ruta_imagen=construir_ruta(cliente_id, firma_id, f"firma.{archivo.extension}"),
            content_type=archivo.content_type,
            tamano_bytes=len(archivo.contenido),
            firma_hash=firma_hash,
            fingerprint_contrato=calcular_fingerprint(
                firma_hash,
                capturada_en,
                cliente_id,
                cotizacion_id,
                producto_id,
                self.proveedor_firma,
            ),
            capturada_en=capturada_en,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

        archivo_guardado = False
        try:
            await self.firmas.reemplazar_capturada(cotizacion_id)
            await self.firmas.crear(firma)
            # El archivo se sube con la fila ya insertada (y bloqueada): si otro request gana la
            # carrera, falla antes de escribir en el almacenamiento.
            await self.almacenamiento.guardar(firma.ruta_imagen, archivo)
            archivo_guardado = True
            await self._commit()
        except FirmaDuplicadaError:
            await self._rollback()
            existente = await self.firmas.obtener_por_idempotency_key(cliente_id, idempotency_key)
            if existente is None:
                raise FirmaConcurrenteError(
                    "Otra firma para la cotización se está procesando."
                ) from None
            return self._repetir(existente, firma_hash, cotizacion_id, producto_id)
        except Exception:
            await self._rollback()
            if archivo_guardado:
                await self.almacenamiento.eliminar(firma.ruta_imagen)
            raise
        return ResultadoCaptura(firma=firma, creada=True)

    @staticmethod
    def _repetir(
        existente: FirmaDigital,
        firma_hash: str,
        cotizacion_id: uuid.UUID,
        producto_id: uuid.UUID,
    ) -> ResultadoCaptura:
        if (
            existente.firma_hash != firma_hash
            or existente.cotizacion_id != cotizacion_id
            or existente.producto_id != producto_id
        ):
            raise IdempotencyKeyReutilizadaError(
                "La clave de idempotencia ya se usó con otra firma o contrato."
            )
        return ResultadoCaptura(firma=existente, creada=False)
