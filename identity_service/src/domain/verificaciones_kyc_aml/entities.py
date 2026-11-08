import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

RUTA_BASE_DOCUMENTOS = "verificaciones-kyc-aml"

_FORMATOS = {
    "image/jpeg": (b"\xff\xd8\xff", "jpg"),
    "image/png": (b"\x89PNG\r\n\x1a\n", "png"),
}


class EstadoVerificacion(str, Enum):
    INICIANDO = "INICIANDO"
    INICIADA = "INICIADA"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    ERROR = "ERROR"


class ResultadoChequeo(str, Enum):
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    PENDIENTE = "PENDIENTE"


class DocumentoInvalidoError(Exception):
    def __init__(self, codigo: str, mensaje: str) -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(mensaje)


@dataclass(frozen=True)
class ArchivoDocumento:
    """Foto de un lado del documento de identidad, validada por tipo real y tamaño."""

    contenido: bytes = field(repr=False)
    content_type: str

    @property
    def extension(self) -> str:
        return _FORMATOS[self.content_type][1]

    def validar(self, tamano_maximo: int) -> None:
        formato = _FORMATOS.get(self.content_type)
        if formato is None:
            raise DocumentoInvalidoError(
                "FORMATO_NO_SOPORTADO", "Los documentos deben ser imágenes JPEG o PNG."
            )
        if not self.contenido:
            raise DocumentoInvalidoError("DOCUMENTO_VACIO", "El documento está vacío.")
        if len(self.contenido) > tamano_maximo:
            raise DocumentoInvalidoError(
                "DOCUMENTO_DEMASIADO_GRANDE", "El documento supera el tamaño permitido."
            )
        if not self.contenido.startswith(formato[0]):
            raise DocumentoInvalidoError(
                "FORMATO_NO_SOPORTADO", "El contenido no corresponde al tipo de archivo."
            )


def calcular_huella(frontal: ArchivoDocumento, reverso: ArchivoDocumento) -> str:
    huella = hashlib.sha256()
    for archivo in (frontal, reverso):
        huella.update(hashlib.sha256(archivo.contenido).digest())
    return huella.hexdigest()


def construir_ruta(cliente_id: uuid.UUID, verificacion_id: uuid.UUID, nombre: str) -> str:
    return f"{RUTA_BASE_DOCUMENTOS}/{cliente_id}/{verificacion_id}/{nombre}"


@dataclass(frozen=True)
class RutasDocumentos:
    frontal: str
    reverso: str


@dataclass(frozen=True)
class ResultadoProveedor:
    kyc: ResultadoChequeo
    aml: ResultadoChequeo
    respuesta: dict


@dataclass(frozen=True)
class InicioProveedor:
    verificacion_externa_id: str
    respuesta: dict


@dataclass
class VerificacionKycAml:
    """Un intento de validación KYC/AML de un cliente (auditoría, una fila por intento)."""

    id: uuid.UUID
    cliente_id: uuid.UUID
    proveedor: str
    huella_documentos: str
    ruta_documento_frontal: str
    ruta_documento_reverso: str
    iniciada_en: datetime
    correlation_id: str
    estado: EstadoVerificacion = EstadoVerificacion.INICIANDO
    idempotency_key: str | None = None
    proveedor_verificacion_id: str | None = None
    resultado_kyc: ResultadoChequeo | None = None
    resultado_aml: ResultadoChequeo | None = None
    respuesta_inicio: dict | None = None
    respuesta_resultado: dict | None = None
    error_codigo: str | None = None
    error_detalle: str | None = None
    resultado_en: datetime | None = None
    version: int = 1

    @property
    def es_final(self) -> bool:
        return self.estado in (EstadoVerificacion.APROBADA, EstadoVerificacion.RECHAZADA)

    def registrar_error(self, codigo: str, detalle: str) -> None:
        self.error_codigo = codigo
        self.error_detalle = detalle[:500]

    def registrar_documentos(self, rutas: RutasDocumentos) -> None:
        self.ruta_documento_frontal = rutas.frontal
        self.ruta_documento_reverso = rutas.reverso

    def marcar_iniciada(self, inicio: InicioProveedor) -> None:
        self.estado = EstadoVerificacion.INICIADA
        self.proveedor_verificacion_id = inicio.verificacion_externa_id
        self.respuesta_inicio = inicio.respuesta
        self.error_codigo = None
        self.error_detalle = None

    def aplicar_resultado(self, resultado: ResultadoProveedor, cuando: datetime) -> None:
        """Rechazo de cualquiera de los chequeos rechaza; aprobar exige ambos aprobados."""
        self.resultado_kyc = resultado.kyc
        self.resultado_aml = resultado.aml
        self.respuesta_resultado = resultado.respuesta
        self.error_codigo = None
        self.error_detalle = None
        if ResultadoChequeo.RECHAZADO in (resultado.kyc, resultado.aml):
            self.estado = EstadoVerificacion.RECHAZADA
        elif resultado.kyc == resultado.aml == ResultadoChequeo.APROBADO:
            self.estado = EstadoVerificacion.APROBADA
        else:
            return
        self.resultado_en = cuando
