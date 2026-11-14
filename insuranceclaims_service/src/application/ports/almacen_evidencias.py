"""Puerto del almacenamiento de evidencias (HU4.1.2). Patrón Valet Key: el servicio firma y verifica;
los archivos van de la app directo al almacenamiento y nunca pasan por los servicios."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


@dataclass(frozen=True)
class CargaPrefirmada:
    url: str
    campos: dict[str, str]
    expira_en: datetime


@dataclass(frozen=True)
class MetadatosObjeto:
    tamano: int
    content_type: str
    cifrado: str | None


class AlmacenNoDisponible(Exception):
    """El almacenamiento no respondió o rechazó las credenciales del servicio."""


class AlmacenEvidenciasPort(Protocol):
    async def generar_carga(self, clave: str, content_type: str, tamano_max: int, ttl: timedelta) -> CargaPrefirmada: ...

    async def metadatos(self, clave: str) -> MetadatosObjeto | None: ...

    async def leer_inicio(self, clave: str, n_bytes: int) -> bytes: ...

    async def eliminar(self, clave: str) -> None: ...
