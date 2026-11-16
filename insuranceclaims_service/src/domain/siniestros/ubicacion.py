from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class FuenteUbicacion(str, Enum):
    GPS = "GPS"
    RED = "RED"
    ULTIMA_CONOCIDA = "ULTIMA_CONOCIDA"


class UbicacionInvalida(ValueError):
    pass


@dataclass(frozen=True)
class UbicacionSiniestro:
    """Dónde ocurrió el evento (HU4.1.2). Las coordenadas nunca se registran en logs."""

    latitud: float
    longitud: float
    precision_m: float
    fuente: FuenteUbicacion
    capturada_en: datetime

    def __post_init__(self) -> None:
        if not -90 <= self.latitud <= 90:
            raise UbicacionInvalida("latitud fuera de rango")
        if not -180 <= self.longitud <= 180:
            raise UbicacionInvalida("longitud fuera de rango")
        if not 0 < self.precision_m <= 5000:
            raise UbicacionInvalida("precisión fuera de rango")
