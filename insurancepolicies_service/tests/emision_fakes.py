"""Dobles de prueba en memoria para la emisión de pólizas y la generación de certificados."""
import copy
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from src.application.ports.cotizaciones import (
    CoberturaCotizada,
    CondicionesEmision,
    CotizacionEmision,
    CotizacionGateway,
    CotizacionNoEncontradaError,
    ImpuestoCotizado,
    ProductoEmision,
)
from src.application.ports.generador_pdf import GeneradorCertificadoPdf
from src.application.ports.titulares import Titular, TitularGateway
from src.domain.certificados.entities import EstadoGeneracion, GeneracionCertificado
from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoRepository,
    CertificadoNoEncontradoError,
    GeneracionCertificadoRepository,
    GeneracionEnCursoDuplicadaError,
)
from src.domain.eventos.entities import EventoOutbox
from src.domain.eventos.repositories import EventoOutboxRepository
from src.domain.firmas.entities import EstadoFirma, FirmaDigital
from src.domain.firmas.repositories import AlmacenamientoFirmaRepository, FirmaDigitalRepository
from src.domain.polizas.entities import ContratoPoliza, EstadoCertificado, Poliza
from src.domain.polizas.repositories import PolizaDuplicadaError, PolizaRepository

CLIENTE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
COTIZACION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
PRODUCTO_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
COBERTURA_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
AHORA = datetime(2026, 11, 13, 14, 0, tzinfo=UTC)
FIRMA_BYTES = b"\x89PNG\r\n\x1a\n" + b"firma-de-prueba"
FIRMA_HASH = hashlib.sha256(FIRMA_BYTES).hexdigest()
RUTA_FIRMA = f"firma-digital/{CLIENTE_ID}/55555555-5555-4555-8555-555555555555/firma.png"


def cotizacion(**cambios) -> CotizacionEmision:
    valores = {
        "cotizacion_id": COTIZACION_ID,
        "cliente_id": CLIENTE_ID,
        "producto_codigo": "VIDA_HIPOTECARIO",
        "moneda": "COP",
        "prima_base": Decimal("1000000.00"),
        "prima_neta": Decimal("1190000.00"),
        "prima_total": Decimal("1416100.00"),
        "impuestos": (ImpuestoCotizado("IVA", Decimal("0.19"), Decimal("226100.00")),),
        "coberturas": (
            CoberturaCotizada(
                COBERTURA_ID,
                "FALLECIMIENTO",
                "Fallecimiento del asegurado",
                Decimal("1416100.00"),
                Decimal("200000000.00"),
                Decimal("0.00"),
            ),
        ),
    }
    return CotizacionEmision(**{**valores, **cambios})


def firma(**cambios) -> FirmaDigital:
    valores = {
        "cliente_id": CLIENTE_ID,
        "cotizacion_id": COTIZACION_ID,
        "producto_id": PRODUCTO_ID,
        "proveedor_firma": "CANVAS_MANUSCRITA",
        "ruta_imagen": RUTA_FIRMA,
        "content_type": "image/png",
        "tamano_bytes": len(FIRMA_BYTES),
        "firma_hash": FIRMA_HASH,
        "fingerprint_contrato": "f" * 64,
        "capturada_en": datetime(2026, 11, 12, 20, 0, tzinfo=UTC),
        "idempotency_key": "k1",
        "correlation_id": "c1",
    }
    return FirmaDigital(**{**valores, **cambios})


class PolizasEnMemoria(PolizaRepository):
    def __init__(self) -> None:
        self.polizas: dict[uuid.UUID, Poliza] = {}
        self.contratos: dict[uuid.UUID, ContratoPoliza] = {}
        self._confirmado = (self.polizas, self.contratos)

    def confirmar(self) -> None:
        self._confirmado = copy.deepcopy((self.polizas, self.contratos))

    def revertir(self) -> None:
        self.polizas, self.contratos = copy.deepcopy(self._confirmado)

    async def guardar(self, poliza: Poliza) -> Poliza:
        for otra in self.polizas.values():
            if otra.cotizacion_id == poliza.cotizacion_id or otra.numero == poliza.numero:
                raise PolizaDuplicadaError()
        self.polizas[poliza.poliza_id] = copy.deepcopy(poliza)
        return poliza

    async def obtener_por_id(self, poliza_id):
        poliza = self.polizas.get(poliza_id)
        return copy.deepcopy(poliza) if poliza else None

    async def obtener_por_numero(self, numero):
        return next((copy.deepcopy(p) for p in self.polizas.values() if p.numero == numero), None)

    async def obtener_por_cotizacion(self, cotizacion_id):
        return next(
            (copy.deepcopy(p) for p in self.polizas.values() if p.cotizacion_id == cotizacion_id),
            None,
        )

    async def listar_por_cliente(self, cliente_id):
        return [copy.deepcopy(p) for p in self.polizas.values() if p.cliente_id == cliente_id]

    async def guardar_contrato(self, contrato):
        self.contratos[contrato.poliza_id] = copy.deepcopy(contrato)

    async def obtener_contrato(self, poliza_id):
        contrato = self.contratos.get(poliza_id)
        return copy.deepcopy(contrato) if contrato else None

    async def actualizar_certificado(self, poliza_id, estado, ruta):
        self.polizas[poliza_id].estado_certificado = estado
        self.polizas[poliza_id].ruta_certificado = ruta


class FirmasEnMemoria(FirmaDigitalRepository):
    def __init__(self, *firmas: FirmaDigital) -> None:
        self.firmas = {f.firma_id: f for f in firmas}
        self.vincular_resultado = True

    async def crear(self, firma):
        raise NotImplementedError

    async def obtener_por_idempotency_key(self, cliente_id, idempotency_key):
        raise NotImplementedError

    async def obtener_activa_por_cotizacion(self, cotizacion_id):
        return next(
            (
                f
                for f in self.firmas.values()
                if f.cotizacion_id == cotizacion_id
                and f.estado in (EstadoFirma.CAPTURADA, EstadoFirma.VINCULADA)
            ),
            None,
        )

    async def obtener_por_poliza(self, poliza_id):
        return next(
            (
                f
                for f in self.firmas.values()
                if f.poliza_id == poliza_id and f.estado == EstadoFirma.VINCULADA
            ),
            None,
        )

    async def reemplazar_capturada(self, cotizacion_id):
        raise NotImplementedError

    async def vincular_a_poliza(self, firma_id, poliza_id):
        if not self.vincular_resultado:
            return False
        self.firmas[firma_id].estado = EstadoFirma.VINCULADA
        self.firmas[firma_id].poliza_id = poliza_id
        return True


class EventosEnMemoria(EventoOutboxRepository):
    def __init__(self) -> None:
        self.eventos: list[EventoOutbox] = []

    async def agregar(self, evento):
        self.eventos.append(evento)

    async def obtener_pendientes(self, limite):
        return self.eventos[:limite]

    async def marcar_publicado(self, evento_id, cuando):
        raise NotImplementedError

    async def registrar_fallo(self, evento_id, detalle):
        raise NotImplementedError


class CotizacionesFalsas(CotizacionGateway):
    def __init__(self) -> None:
        self.cotizacion = cotizacion()
        self.producto = ProductoEmision(
            PRODUCTO_ID, "VIDA_HIPOTECARIO", "Seguro de Vida Deudores Hipotecarios", "VIDA"
        )
        self.condiciones = CondicionesEmision(
            version_condiciones_generales="1.0",
            condiciones_particulares={
                "moneda": "COP",
                "vigencia_propuesta": {
                    "desde": "2026-11-13T13:00:00+00:00",
                    "hasta": "2036-11-13T13:00:00+00:00",
                },
            },
            aceptadas_en=datetime(2026, 11, 12, 19, 0, tzinfo=UTC),
        )
        self.error: Exception | None = None
        self.llamadas: list[tuple[str, str]] = []

    async def obtener_cotizacion(self, cotizacion_id, correlation_id):
        self.llamadas.append(("cotizacion", correlation_id))
        if self.error:
            raise self.error
        if cotizacion_id != self.cotizacion.cotizacion_id:
            raise CotizacionNoEncontradaError(str(cotizacion_id))
        return self.cotizacion

    async def obtener_producto(self, codigo, correlation_id):
        self.llamadas.append(("producto", correlation_id))
        return self.producto

    async def obtener_condiciones(self, cotizacion_id, correlation_id):
        self.llamadas.append(("condiciones", correlation_id))
        return self.condiciones

    async def aclose(self) -> None:
        pass


class TitularesFalsos(TitularGateway):
    def __init__(self) -> None:
        self.titular = Titular("María Fernanda Rodríguez Castañeda", "CC", "1020304050")
        self.error: Exception | None = None

    async def obtener(self, cliente_id, correlation_id):
        if self.error:
            raise self.error
        return self.titular

    async def aclose(self) -> None:
        pass


class GeneracionesEnMemoria(GeneracionCertificadoRepository):
    def __init__(self) -> None:
        self.generaciones: list[GeneracionCertificado] = []
        self._confirmadas: list[GeneracionCertificado] = []

    def confirmar(self) -> None:
        self._confirmadas = copy.deepcopy(self.generaciones)

    def revertir(self) -> None:
        self.generaciones = copy.deepcopy(self._confirmadas)

    async def crear(self, generacion):
        if generacion.estado == EstadoGeneracion.EN_PROCESO and any(
            g.poliza_id == generacion.poliza_id and g.estado == EstadoGeneracion.EN_PROCESO
            for g in self.generaciones
        ):
            raise GeneracionEnCursoDuplicadaError()
        self.generaciones.append(copy.deepcopy(generacion))

    async def actualizar(self, generacion):
        for guardada in self.generaciones:
            if (
                guardada.generacion_id == generacion.generacion_id
                and guardada.estado == EstadoGeneracion.EN_PROCESO
            ):
                guardada.estado = generacion.estado
                guardada.finalizada_en = generacion.finalizada_en
                guardada.ruta_certificado = generacion.ruta_certificado
                guardada.error_codigo = generacion.error_codigo
                guardada.error_detalle = generacion.error_detalle
                return True
        return False

    async def obtener_en_proceso(self, poliza_id):
        return next(
            (
                copy.deepcopy(g)
                for g in self.generaciones
                if g.poliza_id == poliza_id and g.estado == EstadoGeneracion.EN_PROCESO
            ),
            None,
        )

    async def obtener_ultima(self, poliza_id):
        propias = [g for g in self.generaciones if g.poliza_id == poliza_id]
        return copy.deepcopy(propias[-1]) if propias else None


class AlmacenamientoFirmasFalso(AlmacenamientoFirmaRepository):
    def __init__(self, contenido: bytes | None = FIRMA_BYTES) -> None:
        self.contenido = contenido
        self.error: Exception | None = None

    async def guardar(self, ruta, archivo):
        raise NotImplementedError

    async def leer(self, ruta):
        if self.error:
            raise self.error
        return self.contenido

    async def eliminar(self, ruta):
        raise NotImplementedError


class AlmacenamientoCertificadosFalso(AlmacenamientoCertificadoRepository):
    def __init__(self) -> None:
        self.archivos: dict[str, bytes] = {}
        self.error: Exception | None = None

    async def guardar(self, ruta, contenido):
        if self.error:
            raise self.error
        self.archivos[ruta] = contenido

    async def leer(self, ruta):
        if ruta not in self.archivos:
            raise CertificadoNoEncontradoError(ruta)
        return self.archivos[ruta]

    async def eliminar(self, ruta):
        self.archivos.pop(ruta, None)


class GeneradorFalso(GeneradorCertificadoPdf):
    def __init__(self, pdf: bytes = b"%PDF-1.7 falso") -> None:
        self.pdf = pdf
        self.error: Exception | None = None
        self.llamadas: list[tuple[dict, bytes, str]] = []

    @property
    def plantilla(self) -> str:
        return "certificado_poliza.html"

    async def generar(self, datos, firma_bytes, firma_content_type):
        self.llamadas.append((datos, firma_bytes, firma_content_type))
        if self.error:
            raise self.error
        return self.pdf


class Transaccion:
    """Cuenta commits y rollbacks; los participantes confirman o revierten su estado como una BD."""

    def __init__(self, *participantes) -> None:
        self.participantes = participantes
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1
        for participante in self.participantes:
            participante.confirmar()

    async def rollback(self):
        self.rollbacks += 1
        for participante in self.participantes:
            participante.revertir()


def poliza_emitida(estado_certificado=EstadoCertificado.PENDIENTE, **cambios) -> Poliza:
    valores = {
        "cliente_id": CLIENTE_ID,
        "cotizacion_id": COTIZACION_ID,
        "producto_id": PRODUCTO_ID,
        "numero": "POL-20261113-AB12CD34",
        "estado": "EMITIDA",
        "vigencia_desde": datetime(2026, 11, 13, 13, 0, tzinfo=UTC),
        "vigencia_hasta": datetime(2036, 11, 13, 13, 0, tzinfo=UTC),
        "emitida_en": AHORA,
        "ramo": "VIDA",
        "titular_nombre": "María Fernanda Rodríguez Castañeda",
        "estado_certificado": estado_certificado,
    }
    return Poliza(**{**valores, **cambios})


def contrato_de(poliza: Poliza) -> ContratoPoliza:
    return ContratoPoliza(
        poliza_id=poliza.poliza_id,
        datos={
            "moneda": "COP",
            "titular": {
                "nombre": poliza.titular_nombre,
                "tipo_documento": "CC",
                "numero_identificacion": "1020304050",
            },
            "producto": {
                "codigo": "VIDA_HIPOTECARIO",
                "nombre": "Seguro de Vida Deudores Hipotecarios",
                "ramo": "VIDA",
            },
            "coberturas": [
                {
                    "cobertura_id": str(COBERTURA_ID),
                    "codigo": "FALLECIMIENTO",
                    "nombre": "Fallecimiento del asegurado",
                    "limite_asegurado": "200000000.00",
                    "deducible": "0.00",
                    "prima": "1416100.00",
                }
            ],
            "prima": {
                "base": "1000000.00",
                "neta": "1190000.00",
                "impuestos": [{"concepto": "IVA", "tasa": "0.19", "valor": "226100.00"}],
                "total": "1416100.00",
            },
            "condiciones": {
                "version_generales": "1.0",
                "aceptadas_en": "2026-11-12T19:00:00+00:00",
                "particulares": {},
            },
        },
    )


def vinculada(poliza: Poliza) -> FirmaDigital:
    return firma(estado=EstadoFirma.VINCULADA, poliza_id=poliza.poliza_id)


def hace(minutos: int) -> datetime:
    return AHORA - timedelta(minutes=minutos)
