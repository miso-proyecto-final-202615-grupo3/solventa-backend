import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo

from src.application.ports.generador_pdf import GeneracionPdfError, GeneradorCertificadoPdf
from src.application.use_cases.errores_poliza import PolizaNoEncontradaError
from src.domain.certificados.datos import construir_datos_certificado
from src.domain.certificados.entities import (
    EstadoGeneracion,
    GeneracionCertificado,
    construir_ruta_certificado,
)
from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoError,
    AlmacenamientoCertificadoRepository,
    GeneracionCertificadoRepository,
    GeneracionEnCursoDuplicadaError,
)
from src.domain.firmas.repositories import (
    AlmacenamientoFirmaError,
    AlmacenamientoFirmaRepository,
    FirmaDigitalRepository,
)
from src.domain.polizas.entities import EstadoCertificado, Poliza
from src.domain.polizas.repositories import PolizaRepository

logger = logging.getLogger(__name__)

CODIGO_ABANDONADA = "ABANDONADA"


class DatosCertificadoIncompletosError(Exception):
    """A la póliza le falta el contrato o la firma con los que se genera el certificado."""


class FirmaAlteradaError(Exception):
    """La imagen guardada de la firma ya no coincide con el hash registrado al capturarla."""


class GeneracionEnCursoError(Exception):
    """Otro proceso está generando el certificado de la póliza."""


@dataclass(frozen=True)
class ResultadoCertificado:
    poliza: Poliza
    generado: bool


def _codigo_error(exc: Exception) -> str:
    if isinstance(exc, FirmaAlteradaError):
        return "FIRMA_ALTERADA"
    if isinstance(exc, GeneracionPdfError):
        return "PDF_INVALIDO"
    if isinstance(exc, (AlmacenamientoCertificadoError, AlmacenamientoFirmaError)):
        return "ALMACENAMIENTO_NO_DISPONIBLE"
    return "ERROR_INESPERADO"


class GenerarCertificadoPolizaUseCase:
    """Genera el certificado PDF de una póliza emitida y lo deja asociado a ella.

    Es idempotente y deja una fila de auditoría por intento: EN_PROCESO al empezar, y GENERADO o
    FALLIDO al terminar. Ante un fallo relanza la excepción para que SQS reentregue el mensaje.
    """

    def __init__(
        self,
        polizas: PolizaRepository,
        firmas: FirmaDigitalRepository,
        generaciones: GeneracionCertificadoRepository,
        almacenamiento_firmas: AlmacenamientoFirmaRepository,
        almacenamiento_certificados: AlmacenamientoCertificadoRepository,
        generador: GeneradorCertificadoPdf,
        commit: Callable[[], Awaitable[None]],
        rollback: Callable[[], Awaitable[None]],
        zona_horaria: tzinfo,
        en_proceso_ttl: timedelta,
        ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.polizas = polizas
        self.firmas = firmas
        self.generaciones = generaciones
        self.almacenamiento_firmas = almacenamiento_firmas
        self.almacenamiento_certificados = almacenamiento_certificados
        self.generador = generador
        self._commit = commit
        self._rollback = rollback
        self.zona_horaria = zona_horaria
        self.en_proceso_ttl = en_proceso_ttl
        self._ahora = ahora

    async def ejecutar(self, poliza_id, correlation_id: str) -> ResultadoCertificado:
        poliza = await self.polizas.obtener_por_id(poliza_id)
        if poliza is None:
            raise PolizaNoEncontradaError(str(poliza_id))
        if poliza.estado_certificado == EstadoCertificado.GENERADO:
            return ResultadoCertificado(poliza=poliza, generado=False)

        contrato = await self.polizas.obtener_contrato(poliza_id)
        firma = await self.firmas.obtener_por_poliza(poliza_id)
        if contrato is None or firma is None:
            raise DatosCertificadoIncompletosError(
                "La póliza no tiene contrato o firma vinculada para generar el certificado."
            )

        iniciada_en = self._ahora()
        datos = construir_datos_certificado(poliza, contrato, firma, self.zona_horaria, iniciada_en)
        generacion = GeneracionCertificado(
            poliza_id=poliza.poliza_id,
            cliente_id=poliza.cliente_id,
            plantilla=self.generador.plantilla,
            datos_plantilla=datos,
            iniciada_en=iniciada_en,
            correlation_id=correlation_id,
        )
        try:
            await self._cerrar_generacion_abandonada(poliza_id)
            await self.generaciones.crear(generacion)
            await self._commit()
        except GeneracionEnCursoDuplicadaError as exc:
            await self._rollback()
            raise GeneracionEnCursoError("Otro proceso está generando el certificado.") from exc
        except Exception:
            await self._rollback()
            raise

        ruta = construir_ruta_certificado(poliza.cliente_id, poliza.poliza_id)
        try:
            imagen = await self.almacenamiento_firmas.leer(firma.ruta_imagen)
            if hashlib.sha256(imagen).hexdigest() != firma.firma_hash:
                raise FirmaAlteradaError("La imagen de la firma no coincide con su hash registrado.")
            pdf = await self.generador.generar(datos, imagen, firma.content_type)
            await self.almacenamiento_certificados.guardar(ruta, pdf)

            generacion.estado = EstadoGeneracion.GENERADO
            generacion.finalizada_en = self._ahora()
            generacion.ruta_certificado = ruta
            if not await self.generaciones.actualizar(generacion):
                raise GeneracionEnCursoError("La generación fue cerrada por otro proceso.")
            await self.polizas.actualizar_certificado(poliza.poliza_id, EstadoCertificado.GENERADO, ruta)
            await self._commit()
        except Exception as exc:
            await self._rollback()
            await self._registrar_fallo(generacion, exc)
            raise

        poliza.estado_certificado = EstadoCertificado.GENERADO
        poliza.ruta_certificado = ruta
        logger.info(
            "Certificado de la póliza %s generado (correlation_id=%s).",
            poliza.numero,
            correlation_id,
        )
        return ResultadoCertificado(poliza=poliza, generado=True)

    async def _cerrar_generacion_abandonada(self, poliza_id) -> None:
        en_proceso = await self.generaciones.obtener_en_proceso(poliza_id)
        if en_proceso is None:
            return
        if self._ahora() - en_proceso.iniciada_en < self.en_proceso_ttl:
            raise GeneracionEnCursoError("Otro proceso está generando el certificado.")
        en_proceso.estado = EstadoGeneracion.FALLIDO
        en_proceso.finalizada_en = self._ahora()
        en_proceso.error_codigo = CODIGO_ABANDONADA
        en_proceso.error_detalle = "El proceso se interrumpió sin registrar su resultado."
        await self.generaciones.actualizar(en_proceso)

    async def _registrar_fallo(self, generacion: GeneracionCertificado, exc: Exception) -> None:
        if isinstance(exc, GeneracionEnCursoError):
            return
        generacion.estado = EstadoGeneracion.FALLIDO
        generacion.finalizada_en = self._ahora()
        generacion.ruta_certificado = None
        generacion.error_codigo = _codigo_error(exc)
        generacion.error_detalle = f"{type(exc).__name__}: {exc}"[:500]
        try:
            await self.generaciones.actualizar(generacion)
            await self._commit()
        except Exception:
            logger.exception("No se pudo registrar el fallo de la generación %s.", generacion.generacion_id)
            await self._rollback()
