import uuid
from datetime import datetime


def generar_numero(siniestro_id: uuid.UUID, reportado_en: datetime) -> str:
    """Folio legible `SIN-AAAA-XXXXXXXX`, derivado del UUID: no depende de secuencias de la base."""
    return f"SIN-{reportado_en.year}-{siniestro_id.hex[:8].upper()}"
