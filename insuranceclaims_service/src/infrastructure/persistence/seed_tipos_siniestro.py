"""Carga inicial de la tabla `tipo_siniestro` (aprobada el 07/11/2026, plan de HU4.1.1 §4.1).

Idempotente por `(producto_codigo, codigo)`: crea las filas que faltan y actualiza las existentes.
Los productos de vida (`MICROSEGURO_VIDA`, `VIDA_HIPOTECARIO`) no tienen filas: no se reportan por la app.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import invalidar_cache
from src.infrastructure.persistence.models import TipoSiniestroModel

logger = logging.getLogger(__name__)

# (producto_codigo, codigo, nombre, nombre_en, fotos_max, videos_max, orden)
TIPOS_SINIESTRO: tuple[tuple[str, str, str, str, int, int, int], ...] = (
    ("SEGURO_VIAJE", "GASTO_MEDICO", "Gasto médico", "Medical expense", 5, 0, 1),
    ("SEGURO_VIAJE", "EQUIPAJE", "Pérdida o daño de equipaje", "Lost or damaged luggage", 5, 1, 2),
    ("SEGURO_VIAJE", "CANCELACION_VIAJE", "Cancelación del viaje", "Trip cancellation", 3, 0, 3),
    ("PROTECCION_DISPOSITIVOS", "DANO_DISPOSITIVO", "Daño al dispositivo", "Device damage", 5, 1, 1),
    ("PROTECCION_DISPOSITIVOS", "ROBO", "Robo", "Theft", 3, 1, 2),
)


async def sembrar_tipos_siniestro(session: AsyncSession) -> int:
    """Crea o actualiza las filas del catálogo. Retorna cuántas creó. No hace commit."""
    existentes = {
        (m.producto_codigo, m.codigo): m for m in (await session.scalars(select(TipoSiniestroModel))).all()
    }
    creados = 0
    for producto, codigo, nombre, nombre_en, fotos, videos, orden in TIPOS_SINIESTRO:
        modelo = existentes.get((producto, codigo))
        if modelo is None:
            session.add(
                TipoSiniestroModel(
                    producto_codigo=producto, codigo=codigo, nombre=nombre, nombre_en=nombre_en,
                    fotos_max=fotos, videos_max=videos, activo=True, orden=orden,
                )
            )
            creados += 1
        else:
            modelo.nombre, modelo.nombre_en = nombre, nombre_en
            modelo.fotos_max, modelo.videos_max, modelo.orden = fotos, videos, orden
    await session.flush()
    invalidar_cache()
    logger.info("tipos_siniestro_sembrados creados=%d total=%d", creados, len(TIPOS_SINIESTRO))
    return creados
