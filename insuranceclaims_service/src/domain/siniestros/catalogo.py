"""Catálogo de tipos de siniestro por producto.

La fuente única es la tabla `tipo_siniestro` (decisión S4 de HU4.1.1): los casos de uso, el BFF,
la web y el back-office la leen a través de este puerto o de `GET /tipos-siniestro`; nadie copia
la lista en código. Un producto sin tipos activos no se puede reportar desde la app.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

IDIOMA_POR_DEFECTO = "es"


@dataclass(frozen=True)
class ReglasEvidencia:
    fotos_max: int
    videos_max: int

    @property
    def admite_video(self) -> bool:
        return self.videos_max > 0


@dataclass(frozen=True)
class TipoSiniestro:
    producto_codigo: str
    codigo: str
    nombre: str
    reglas: ReglasEvidencia


def idioma_de(accept_language: str | None) -> str:
    """`en` si el primer idioma pedido es inglés; si no, español."""
    if not accept_language:
        return IDIOMA_POR_DEFECTO
    primero = accept_language.split(",")[0].strip().lower()
    return "en" if primero.startswith("en") else IDIOMA_POR_DEFECTO


class CatalogoTiposSiniestro(ABC):
    @abstractmethod
    async def listar(self, producto_codigo: str | None = None, idioma: str = IDIOMA_POR_DEFECTO) -> list[TipoSiniestro]:
        """Tipos activos en orden de pantalla, de un producto o de todos."""

    async def tipos_de(self, producto_codigo: str, idioma: str = IDIOMA_POR_DEFECTO) -> list[TipoSiniestro]:
        return await self.listar(producto_codigo, idioma)

    async def obtener(
        self, producto_codigo: str, tipo_codigo: str, idioma: str = IDIOMA_POR_DEFECTO
    ) -> TipoSiniestro | None:
        return next((t for t in await self.listar(producto_codigo, idioma) if t.codigo == tipo_codigo), None)
