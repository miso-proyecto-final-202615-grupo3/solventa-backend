import uuid
from datetime import UTC, datetime

from src.domain.siniestros.folio import generar_numero


def test_folio_usa_el_anio_del_reporte_y_el_inicio_del_uuid():
    siniestro_id = uuid.UUID("c41f0e2a-9b7d-4e55-8a0c-2f6d1b3e9a77")

    assert generar_numero(siniestro_id, datetime(2026, 11, 10, tzinfo=UTC)) == "SIN-2026-C41F0E2A"


def test_folio_cabe_en_la_columna():
    assert len(generar_numero(uuid.uuid4(), datetime.now(UTC))) <= 20
