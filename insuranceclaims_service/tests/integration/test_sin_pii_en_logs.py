import logging
import uuid

from tests.fakes import CLIENTE
from tests.integration.test_siniestros_api import BASE, HEADERS, _body, api  # noqa: F401

DESCRIPCION = "Descripción privada del evento con datos personales."


async def test_un_reporte_completo_no_registra_la_descripcion(api, caplog):  # noqa: F811
    client, _ = api
    caplog.set_level(logging.INFO)

    creado = await client.post(
        f"{BASE}/siniestros",
        json=_body(descripcion=DESCRIPCION),
        headers={**HEADERS, "Idempotency-Key": str(uuid.uuid4())},
    )
    await client.get(f"{BASE}/siniestros/{creado.json()['siniestro_id']}", headers=HEADERS)

    assert creado.status_code == 201
    assert DESCRIPCION not in caplog.text
    assert str(CLIENTE) not in caplog.text
    assert "siniestro_reportado" in caplog.text
