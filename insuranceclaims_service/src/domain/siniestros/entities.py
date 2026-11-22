import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from src.domain.siniestros.enums import CanalReporte
from src.domain.siniestros.ubicacion import FuenteUbicacion, UbicacionSiniestro
from src.domain.siniestros.errores import TransicionInvalida


@dataclass
class EventoExterno:
    event_id: str
    fuente: str
    tipo: str
    checksum: str
    ocurrido_en: datetime
    recibido_en: datetime
    payload_referencia: str
    estado: str = "RECIBIDO"
    intentos: int = 0
    ultimo_error: str | None = None
    datos: dict | None = None
    resultado: list | None = None
    procesado_en: datetime | None = None
    evento_externo_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class EventoOutbox:
    tipo: str
    agregado_id: uuid.UUID
    payload: dict
    estado: str = "PENDIENTE"
    intentos: int = 0
    ultimo_error: str | None = None
    creado_en: datetime | None = None
    publicado_en: datetime | None = None
    evento_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class ActivacionParametrica:
    evento_externo_id: uuid.UUID
    cobertura_id: uuid.UUID
    regla_aplicada: str
    estado: str
    clave_idempotencia: str
    activada_en: datetime
    activacion_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class ActivacionPoliza:
    activacion_id: uuid.UUID
    poliza_id: uuid.UUID
    estado: str
    clave_idempotencia: str
    identificada_en: datetime
    activacion_poliza_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Siniestro:
    poliza_id: uuid.UUID
    tipo: str
    estado: str
    clave_idempotencia: str
    ocurrido_en: datetime
    reportado_en: datetime
    activacion_id: uuid.UUID | None = None
    evidencia_referencia: dict | list | None = None
    # Siniestro asistido reportado por el cliente (HU4.1.1).
    cliente_id: uuid.UUID | None = None
    numero: str | None = None
    canal: str = CanalReporte.PARAMETRICO.value
    descripcion: str | None = None
    poliza_numero: str | None = None
    producto_codigo: str | None = None
    huella_solicitud: str | None = None
    # Ubicación del evento (HU4.1.2). Plana para el repositorio genérico; se lee con `ubicacion`.
    ubicacion_latitud: Decimal | None = None
    ubicacion_longitud: Decimal | None = None
    ubicacion_precision_m: Decimal | None = None
    ubicacion_fuente: str | None = None
    ubicacion_capturada_en: datetime | None = None
    ubicacion_actualizada_en: datetime | None = None
    estado_actualizado_en: datetime | None = None
    siniestro_id: uuid.UUID = field(default_factory=uuid.uuid4)

    @property
    def ubicacion(self) -> UbicacionSiniestro | None:
        if self.ubicacion_latitud is None or self.ubicacion_longitud is None:
            return None
        return UbicacionSiniestro(
            latitud=float(self.ubicacion_latitud),
            longitud=float(self.ubicacion_longitud),
            precision_m=float(self.ubicacion_precision_m or 0),
            fuente=FuenteUbicacion(self.ubicacion_fuente),
            capturada_en=self.ubicacion_capturada_en,
        )

    def registrar_ubicacion(self, ubicacion: UbicacionSiniestro, ahora: datetime) -> None:
        """Reemplaza la ubicación del evento (una por siniestro, decisión E5)."""
        self.ubicacion_latitud = Decimal(str(round(ubicacion.latitud, 6)))
        self.ubicacion_longitud = Decimal(str(round(ubicacion.longitud, 6)))
        self.ubicacion_precision_m = Decimal(str(round(ubicacion.precision_m, 2)))
        self.ubicacion_fuente = ubicacion.fuente.value
        self.ubicacion_capturada_en = ubicacion.capturada_en
        self.ubicacion_actualizada_en = ahora

    def cambiar_estado(self, nuevo: str, ahora: datetime) -> bool:
        """Aplica la máquina de estados del siniestro. Repetir el estado es idempotente."""
        if nuevo == self.estado:
            return False
        transiciones = {
            "REPORTADO": {"EN_EVALUACION"},
            "EN_EVALUACION": {"APROBADO", "RECHAZADO"},
            "APROBADO": {"PAGADO"},
        }
        if nuevo not in transiciones.get(self.estado, set()):
            raise TransicionInvalida("El siniestro no admite este cambio de estado.")
        self.estado = nuevo
        self.estado_actualizado_en = ahora
        return True


@dataclass
class Indemnizacion:
    siniestro_id: uuid.UUID
    monto_aprobado: Decimal
    moneda: str
    estado: str
    aprobada_en: datetime | None = None
    indemnizacion_id: uuid.UUID = field(default_factory=uuid.uuid4)
