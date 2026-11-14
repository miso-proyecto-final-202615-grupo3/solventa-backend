"""Evidencias de un siniestro (HU4.1.2): cada foto o video es independiente y tiene su propio estado."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.domain.siniestros.errores import TransicionInvalida


class TipoEvidencia(str, Enum):
    FOTO = "FOTO"
    VIDEO = "VIDEO"


class OrigenEvidencia(str, Enum):
    CAMARA = "CAMARA"
    GALERIA = "GALERIA"


class EstadoEvidencia(str, Enum):
    PENDIENTE = "PENDIENTE"
    CARGADA = "CARGADA"
    RECHAZADA = "RECHAZADA"
    EXPIRADA = "EXPIRADA"


EXTENSIONES = {TipoEvidencia.FOTO: "jpg", TipoEvidencia.VIDEO: "mp4"}


def clave_objeto(prefijo: str, siniestro_id: uuid.UUID, evidencia_id: uuid.UUID, tipo: TipoEvidencia) -> str:
    """Llave en el almacenamiento. Nunca contiene datos del cliente."""
    return f"{prefijo}{siniestro_id}/evidencias/{evidencia_id}.{EXTENSIONES[tipo]}"


@dataclass
class EvidenciaSiniestro:
    """Máquina de estados: PENDIENTE → CARGADA | RECHAZADA | EXPIRADA, y PENDIENTE | EXPIRADA → PENDIENTE
    al renovar la carga (reintento con la misma clave). Cualquier otra transición falla."""

    siniestro_id: uuid.UUID
    tipo: str
    content_type: str
    tamano_declarado: int
    origen: str
    capturada_en: datetime
    objeto_clave: str
    estado: str
    solicitada_en: datetime
    expira_en: datetime
    tamano_bytes: int | None = None
    cargada_en: datetime | None = None
    motivo_rechazo: str | None = None
    evidencia_id: uuid.UUID = field(default_factory=uuid.uuid4)
    # Clave que manda la app por evidencia local: reintentar la solicitud reutiliza esta fila.
    clave_idempotencia: str | None = None

    @property
    def pendiente(self) -> bool:
        return self.estado == EstadoEvidencia.PENDIENTE.value

    def vencida(self, ahora: datetime) -> bool:
        return self.pendiente and _comparable(self.expira_en, ahora) <= ahora

    def confirmar(self, tamano: int, ahora: datetime) -> None:
        self._exigir_pendiente()
        self.estado = EstadoEvidencia.CARGADA.value
        self.tamano_bytes = tamano
        self.cargada_en = ahora

    def rechazar(self, motivo: str) -> None:
        self._exigir_pendiente()
        self.estado = EstadoEvidencia.RECHAZADA.value
        self.motivo_rechazo = motivo

    def expirar_si_vencida(self, ahora: datetime) -> bool:
        if not self.vencida(ahora):
            return False
        self.estado = EstadoEvidencia.EXPIRADA.value
        return True

    def renovar(self, tamano_declarado: int, expira_en: datetime) -> None:
        """Otra carga para la misma evidencia (reintento de la app): vuelve a PENDIENTE con un plazo nuevo."""
        if self.estado not in (EstadoEvidencia.PENDIENTE.value, EstadoEvidencia.EXPIRADA.value):
            raise TransicionInvalida(f"La evidencia está {self.estado}.")
        self.estado = EstadoEvidencia.PENDIENTE.value
        self.tamano_declarado = tamano_declarado
        self.expira_en = expira_en

    def _exigir_pendiente(self) -> None:
        if not self.pendiente:
            raise TransicionInvalida(f"La evidencia está {self.estado}.")


def _comparable(valor: datetime, referencia: datetime) -> datetime:
    # SQLite devuelve fechas sin zona; se interpretan con la zona de la referencia (UTC).
    if valor.tzinfo is None and referencia.tzinfo is not None:
        return valor.replace(tzinfo=referencia.tzinfo)
    return valor
