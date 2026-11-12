import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

RUTA_BASE_FIRMAS = "firma-digital"
VERSION_FINGERPRINT = "v1"

_FORMATOS = {
    "image/png": (b"\x89PNG\r\n\x1a\n", "png"),
    "image/jpeg": (b"\xff\xd8\xff", "jpg"),
}


class EstadoFirma(StrEnum):
    CAPTURADA = "CAPTURADA"
    REEMPLAZADA = "REEMPLAZADA"
    VINCULADA = "VINCULADA"


class FirmaInvalidaError(Exception):
    def __init__(self, codigo: str, mensaje: str) -> None:
        self.codigo = codigo
        self.mensaje = mensaje
        super().__init__(mensaje)


@dataclass(frozen=True)
class ArchivoFirma:
    """Imagen de la firma manuscrita, validada por tipo real y tamaño."""

    contenido: bytes = field(repr=False)
    content_type: str

    @property
    def extension(self) -> str:
        return _FORMATOS[self.content_type][1]

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.contenido).hexdigest()

    def validar(self, tamano_maximo: int) -> None:
        formato = _FORMATOS.get(self.content_type)
        if formato is None:
            raise FirmaInvalidaError(
                "FORMATO_NO_SOPORTADO", "La firma debe ser una imagen PNG o JPEG."
            )
        if not self.contenido:
            raise FirmaInvalidaError("FIRMA_VACIA", "La imagen de la firma está vacía.")
        if len(self.contenido) > tamano_maximo:
            raise FirmaInvalidaError(
                "FIRMA_DEMASIADO_GRANDE", "La imagen de la firma supera el tamaño permitido."
            )
        if not self.contenido.startswith(formato[0]):
            raise FirmaInvalidaError(
                "FORMATO_NO_SOPORTADO", "El contenido no corresponde al tipo de archivo."
            )


def construir_ruta(cliente_id: uuid.UUID, firma_id: uuid.UUID, nombre: str) -> str:
    """Ruta relativa, igual en disco local y en S3."""
    return f"{RUTA_BASE_FIRMAS}/{cliente_id}/{firma_id}/{nombre}"


def calcular_fingerprint(
    firma_hash: str,
    capturada_en: datetime,
    cliente_id: uuid.UUID,
    cotizacion_id: uuid.UUID,
    producto_id: uuid.UUID,
    proveedor_firma: str,
) -> str:
    """SHA-256 de la serialización canónica de los datos que identifican el contrato firmado."""
    momento = capturada_en.astimezone(UTC).isoformat(timespec="microseconds")
    campos = (
        VERSION_FINGERPRINT,
        firma_hash,
        momento,
        str(cliente_id),
        str(cotizacion_id),
        str(producto_id),
        proveedor_firma,
    )
    return hashlib.sha256("|".join(campos).encode("utf-8")).hexdigest()


@dataclass
class FirmaDigital:
    cliente_id: uuid.UUID
    cotizacion_id: uuid.UUID
    producto_id: uuid.UUID
    proveedor_firma: str
    ruta_imagen: str
    content_type: str
    tamano_bytes: int
    firma_hash: str
    fingerprint_contrato: str
    capturada_en: datetime
    idempotency_key: str
    correlation_id: str
    estado: EstadoFirma = EstadoFirma.CAPTURADA
    poliza_id: uuid.UUID | None = None
    firma_id: uuid.UUID = field(default_factory=uuid.uuid4)
