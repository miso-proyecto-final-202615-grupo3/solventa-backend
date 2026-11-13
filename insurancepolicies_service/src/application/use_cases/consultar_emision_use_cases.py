import uuid
from dataclasses import dataclass
from decimal import Decimal

from src.application.use_cases.errores_poliza import (
    AccesoPolizaDenegadoError,
    PolizaNoEncontradaError,
)
from src.domain.certificados.entities import GeneracionCertificado
from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoRepository,
    GeneracionCertificadoRepository,
)
from src.domain.polizas.entities import EstadoCertificado, Poliza
from src.domain.polizas.repositories import PolizaRepository


class CertificadoNoGeneradoError(Exception):
    """El certificado de la póliza todavía no está disponible."""

    def __init__(self, estado: EstadoCertificado) -> None:
        self.estado = estado
        super().__init__(f"El certificado está {estado.value}.")


@dataclass(frozen=True)
class ResumenPoliza:
    poliza: Poliza
    moneda: str | None

    @property
    def prima(self) -> Decimal:
        return self.poliza.prima_total


@dataclass(frozen=True)
class EstadoCertificadoPoliza:
    poliza: Poliza
    ultima_generacion: GeneracionCertificado | None


@dataclass(frozen=True)
class CertificadoDescargable:
    contenido: bytes
    nombre_archivo: str


def _verificar_titular(poliza: Poliza | None, cliente_id: uuid.UUID, referencia: str) -> Poliza:
    if poliza is None:
        raise PolizaNoEncontradaError(referencia)
    if poliza.cliente_id != cliente_id:
        raise AccesoPolizaDenegadoError(referencia)
    return poliza


class ConsultarPolizaPorCotizacionUseCase:
    def __init__(self, polizas: PolizaRepository) -> None:
        self.polizas = polizas

    async def ejecutar(self, cotizacion_id: uuid.UUID, cliente_id: uuid.UUID) -> ResumenPoliza:
        poliza = _verificar_titular(
            await self.polizas.obtener_por_cotizacion(cotizacion_id), cliente_id, str(cotizacion_id)
        )
        contrato = await self.polizas.obtener_contrato(poliza.poliza_id)
        moneda = contrato.datos.get("moneda") if contrato else None
        return ResumenPoliza(poliza=poliza, moneda=moneda)


class ConsultarEstadoCertificadoUseCase:
    def __init__(self, polizas: PolizaRepository, generaciones: GeneracionCertificadoRepository) -> None:
        self.polizas = polizas
        self.generaciones = generaciones

    async def ejecutar(self, poliza_id: uuid.UUID, cliente_id: uuid.UUID) -> EstadoCertificadoPoliza:
        poliza = _verificar_titular(
            await self.polizas.obtener_por_id(poliza_id), cliente_id, str(poliza_id)
        )
        return EstadoCertificadoPoliza(
            poliza=poliza, ultima_generacion=await self.generaciones.obtener_ultima(poliza_id)
        )


class DescargarCertificadoUseCase:
    def __init__(
        self, polizas: PolizaRepository, almacenamiento: AlmacenamientoCertificadoRepository
    ) -> None:
        self.polizas = polizas
        self.almacenamiento = almacenamiento

    async def ejecutar(self, poliza_id: uuid.UUID, cliente_id: uuid.UUID) -> CertificadoDescargable:
        poliza = _verificar_titular(
            await self.polizas.obtener_por_id(poliza_id), cliente_id, str(poliza_id)
        )
        if poliza.estado_certificado != EstadoCertificado.GENERADO or not poliza.ruta_certificado:
            raise CertificadoNoGeneradoError(poliza.estado_certificado)
        contenido = await self.almacenamiento.leer(poliza.ruta_certificado)
        return CertificadoDescargable(
            contenido=contenido, nombre_archivo=f"certificado-{poliza.numero}.pdf"
        )
