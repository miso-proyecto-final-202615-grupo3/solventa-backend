import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.siniestros.catalogo import (
    IDIOMA_POR_DEFECTO,
    CatalogoTiposSiniestro,
    ReglasEvidencia,
    TipoSiniestro,
)
from src.infrastructure.persistence.models import TipoSiniestroModel

CACHE_TTL_SECONDS = 300


@dataclass(frozen=True)
class _Fila:
    producto_codigo: str
    codigo: str
    nombre: str
    nombre_en: str
    fotos_max: int
    videos_max: int
    orden: int


# La tabla casi no cambia: se lee completa y se guarda en memoria del proceso por 5 minutos.
_cache: tuple[float, list[_Fila]] | None = None


def invalidar_cache() -> None:
    global _cache
    _cache = None


class SqlAlchemyCatalogoTiposSiniestro(CatalogoTiposSiniestro):
    def __init__(self, session: AsyncSession, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
        self.session = session
        self.ttl_seconds = ttl_seconds

    async def listar(self, producto_codigo: str | None = None, idioma: str = IDIOMA_POR_DEFECTO) -> list[TipoSiniestro]:
        filas = await self._filas_activas()
        return [
            TipoSiniestro(
                producto_codigo=fila.producto_codigo,
                codigo=fila.codigo,
                nombre=fila.nombre_en if idioma == "en" else fila.nombre,
                reglas=ReglasEvidencia(fotos_max=fila.fotos_max, videos_max=fila.videos_max),
            )
            for fila in filas
            if producto_codigo is None or fila.producto_codigo == producto_codigo
        ]

    async def _filas_activas(self) -> list[_Fila]:
        global _cache
        ahora = time.monotonic()
        if _cache is not None and ahora - _cache[0] < self.ttl_seconds:
            return _cache[1]
        modelos = (
            await self.session.scalars(
                select(TipoSiniestroModel)
                .where(TipoSiniestroModel.activo.is_(True))
                .order_by(TipoSiniestroModel.producto_codigo, TipoSiniestroModel.orden, TipoSiniestroModel.codigo)
            )
        ).all()
        filas = [
            _Fila(m.producto_codigo, m.codigo, m.nombre, m.nombre_en, m.fotos_max, m.videos_max, m.orden)
            for m in modelos
        ]
        _cache = (ahora, filas)
        return filas
