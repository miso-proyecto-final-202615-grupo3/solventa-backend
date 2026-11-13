import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# create_all no altera tablas que ya existen: los cambios sobre `poliza` se aplican aquí, de forma
# idempotente. Cada sentencia corre en su propia transacción, así que una que falle (p. ej. el
# índice único si ya hay cotizaciones duplicadas) no impide aplicar las demás ni arrancar.
MIGRACIONES = (
    "ALTER TABLE insurancepolicies.poliza "
    "ADD COLUMN IF NOT EXISTS ramo VARCHAR(80) NOT NULL DEFAULT 'SEGURO'",
    "ALTER TABLE insurancepolicies.poliza "
    "ADD COLUMN IF NOT EXISTS titular_nombre VARCHAR(200) NOT NULL DEFAULT ''",
    "ALTER TABLE insurancepolicies.poliza "
    "ADD COLUMN IF NOT EXISTS estado_certificado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'",
    "ALTER TABLE insurancepolicies.poliza "
    "ADD COLUMN IF NOT EXISTS ruta_certificado VARCHAR(512)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_poliza_cotizacion_id "
    "ON insurancepolicies.poliza (cotizacion_id)",
)


async def aplicar_migraciones(engine: AsyncEngine) -> None:
    for sentencia in MIGRACIONES:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(sentencia))
        except Exception:
            logger.warning("No se pudo aplicar la migración: %s", sentencia, exc_info=True)
