"""HU4.2.3 · Siniestro paramétrico de punta a punta: ingesta → consumidor → siniestro, indemnización, pago y push."""
import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.config import settings
from src.core.database import Base
from src.infrastructure.messaging.procesador_eventos_parametricos import ProcesadorEventosParametricos
from src.infrastructure.persistence.models import (
    ActivacionParametricaModel,
    ActivacionPolizaModel,
    EventoExternoModel,
    EventoOutboxModel,
    IndemnizacionModel,
    SiniestroModel,
)
from src.main import app
from src.presentation.dependencies import get_db, get_polizas_port, get_reloj
from tests.fakes import CLIENTE, OTRO_CLIENTE, PolizasFalsas, poliza

BASE = "/api/v1/insuranceclaims-service"
FUENTE = {"X-Fuente-Token": "token-fuente-de-prueba"}
OPERADOR = {"X-Operador-Token": "token-operador-de-prueba"}
AHORA = datetime(2026, 11, 21, 20, 0, tzinfo=UTC)
PARAMETRICA = poliza(producto_codigo="SEGURO_PARAMETRICO", producto_nombre="Seguro paramétrico", numero="SLV-PARAM-1")
OTRA = poliza(
    poliza_id=uuid.UUID("9a3c7d2f-5b8e-4a10-8b62-1d7c2e0f3a21"), cliente_id=OTRO_CLIENTE, numero="SLV-PARAM-2",
    producto_codigo="SEGURO_PARAMETRICO",
)
NO_PARAMETRICA = poliza(poliza_id=uuid.UUID("1c5e9f4b-7d0a-4c32-ad84-3f9e4a2b5c43"))
VENCIDA = poliza(
    poliza_id=uuid.UUID("0b4d8e3a-6c9f-4b21-9c73-2e8d3f1a4b32"), numero="SLV-PARAM-3",
    producto_codigo="SEGURO_PARAMETRICO", vigencia_hasta=date(2026, 6, 1),
)


def _evento(event_id="IDEAM-BOG-0001", mm=72.5, zona="BOGOTA", tipo="LLUVIA", datos=None) -> dict:
    return {
        "event_id": event_id, "fuente": "IDEAM", "tipo": tipo, "ocurrido_en": "2026-11-21T10:00:00-05:00",
        "datos": datos if datos is not None else {"zona": zona, "precipitacion_mm": mm},
    }


@pytest.fixture
async def entorno(monkeypatch):
    monkeypatch.setattr(settings, "EVENTOS_FUENTE_TOKEN", FUENTE["X-Fuente-Token"])
    monkeypatch.setattr(settings, "OPERADOR_TOKEN", OPERADOR["X-Operador-Token"])
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"insuranceclaims": None}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    polizas = PolizasFalsas(PARAMETRICA, OTRA, VENCIDA, NO_PARAMETRICA)

    async def db_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_polizas_port] = lambda: polizas
    app.dependency_overrides[get_reloj] = lambda: (lambda: AHORA)
    procesador = ProcesadorEventosParametricos(factory, polizas, lambda: AHORA, ["EMITIDA", "VIGENTE"], 0.01, 3)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory, procesador, polizas
    app.dependency_overrides.clear()
    await engine.dispose()


async def _suscribir(client, p, cobertura="LLUVIA_EXTREMA", indice="Bogota", umbral=50, monto=300000):
    return await client.put(
        f"{BASE}/polizas-parametricas/{p.poliza_id}", headers=OPERADOR,
        json={"cliente_id": str(p.cliente_id), "cobertura": cobertura, "indice": indice,
              "umbral": umbral, "monto_compensacion": monto},
    )


async def _filas(factory, modelo):
    async with factory() as session:
        return list((await session.scalars(select(modelo))).all())


async def test_ingesta_requiere_token_y_es_idempotente(entorno):
    client, factory, _, _ = entorno

    sin_token = await client.post(f"{BASE}/eventos-parametricos", json=_evento())
    nuevo = await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)
    repetido = await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)
    conflicto = await client.post(f"{BASE}/eventos-parametricos", json=_evento(mm=10), headers=FUENTE)

    assert sin_token.status_code == 403
    assert nuevo.status_code == 202
    assert nuevo.json() == {"event_id": "IDEAM-BOG-0001", "estado": "RECIBIDO", "recibido_en": "2026-11-21T20:00:00Z"}
    assert repetido.status_code == 200
    assert conflicto.status_code == 409
    assert conflicto.json()["detail"]["codigo"] == "EVENTO_EN_CONFLICTO"
    assert len(await _filas(factory, EventoExternoModel)) == 1


@pytest.mark.parametrize(
    "cuerpo",
    [
        _evento(datos={"zona": "BOGOTA"}),
        _evento(tipo="GRANIZO"),
        {**_evento(), "ocurrido_en": "2026-11-21T10:00:00"},
        {**_evento(), "extra": 1},
    ],
)
async def test_contrato_invalido_no_entra_al_bus(entorno, cuerpo):
    client, factory, _, _ = entorno

    response = await client.post(f"{BASE}/eventos-parametricos", json=cuerpo, headers=FUENTE)

    assert response.status_code == 422
    assert await _filas(factory, EventoExternoModel) == []


async def test_suscripcion_valida_la_poliza_con_polizas(entorno):
    client, _, _, _ = entorno

    ok = await _suscribir(client, PARAMETRICA)
    no_parametrica = await _suscribir(client, NO_PARAMETRICA)
    ajena = await client.put(
        f"{BASE}/polizas-parametricas/{PARAMETRICA.poliza_id}", headers=OPERADOR,
        json={"cliente_id": str(OTRO_CLIENTE), "cobertura": "LLUVIA_EXTREMA", "indice": "BOGOTA", "monto_compensacion": 1},
    )
    sin_token = await client.put(f"{BASE}/polizas-parametricas/{PARAMETRICA.poliza_id}", json={})

    assert ok.status_code == 200, ok.text
    assert ok.json()["indice"] == "BOGOTA" and ok.json()["poliza_numero"] == "SLV-PARAM-1"
    assert no_parametrica.status_code == 422 and no_parametrica.json()["detail"]["codigo"] == "POLIZA_NO_PARAMETRICA"
    assert ajena.status_code == 404
    assert sin_token.status_code == 403


async def test_evento_cubierto_crea_siniestro_indemnizacion_pago_y_notificacion(entorno):
    client, factory, procesador, _ = entorno
    await _suscribir(client, PARAMETRICA, umbral=50, monto=300000)
    await _suscribir(client, OTRA, umbral=90)            # bajo umbral
    await _suscribir(client, VENCIDA, umbral=10)         # fuera de vigencia
    await client.post(f"{BASE}/eventos-parametricos", json=_evento(mm=72.5), headers=FUENTE)

    assert await procesador.procesar_pendientes() == 1

    siniestros = await _filas(factory, SiniestroModel)
    assert len(siniestros) == 1
    siniestro = siniestros[0]
    assert (siniestro.canal, siniestro.estado, siniestro.tipo, siniestro.cliente_id) == (
        "PARAMETRICO", "APROBADO", "LLUVIA_EXTREMA", CLIENTE,
    )
    assert siniestro.numero.startswith("SIN-2026-") and siniestro.activacion_id is not None
    assert "72.5 mm en BOGOTA" in siniestro.descripcion
    [indemnizacion] = await _filas(factory, IndemnizacionModel)
    assert (str(indemnizacion.monto_aprobado), indemnizacion.estado) == ("300000.00", "PAGO_SOLICITADO")
    assert len(await _filas(factory, ActivacionParametricaModel)) == 1
    assert len(await _filas(factory, ActivacionPolizaModel)) == 1
    outbox = {e.tipo: e.payload for e in await _filas(factory, EventoOutboxModel)}
    assert outbox["SINIESTRO_ESTADO"] == {
        "tipo": "SINIESTRO_ESTADO", "siniestro_id": str(siniestro.siniestro_id), "numero": siniestro.numero,
        "estado": "APROBADO", "canal": "PARAMETRICO",
    }
    pago = outbox["PAGO_INDEMNIZACION_SOLICITADO"]
    assert (pago["monto"], pago["moneda"], pago["cliente_id"]) == ("300000.00", "COP", str(CLIENTE))
    assert pago["clave_idempotencia"].startswith("PAGO:PARAM:IDEAM-BOG-0001:LLUVIA_EXTREMA:")

    traza = (await client.get(f"{BASE}/eventos-parametricos/IDEAM-BOG-0001", headers=FUENTE)).json()
    assert traza["estado"] == "PROCESADO" and traza["procesado_en"] == "2026-11-21T20:00:00Z"
    assert {r["poliza_numero"]: r["resultado"] for r in traza["resultado"]} == {
        "SLV-PARAM-1": "ACTIVADA", "SLV-PARAM-2": "BAJO_UMBRAL", "SLV-PARAM-3": "POLIZA_NO_VIGENTE",
    }

    # El cliente lo ve en su detalle con la compensación (y la lista lo marca como paramétrico).
    detalle = (await client.get(f"{BASE}/siniestros/{siniestro.siniestro_id}", headers={"X-Cliente-Id": str(CLIENTE)})).json()
    assert detalle["canal"] == "PARAMETRICO"
    assert detalle["indemnizacion"] == {"monto": "300000.00", "moneda": "COP", "estado": "PAGO_SOLICITADO"}
    lista = (await client.get(f"{BASE}/siniestros", headers={"X-Cliente-Id": str(CLIENTE)})).json()
    assert lista["siniestros"][0]["canal"] == "PARAMETRICO"

    # Pagado por el operador → la indemnización queda PAGADA.
    pagado = await client.put(f"{BASE}/siniestros/{siniestro.siniestro_id}/estado", json={"estado": "PAGADO"}, headers=OPERADOR)
    assert pagado.status_code == 200
    [indemnizacion] = await _filas(factory, IndemnizacionModel)
    assert indemnizacion.estado == "PAGADA"


async def test_reprocesar_el_mismo_evento_no_duplica(entorno):
    client, factory, procesador, _ = entorno
    await _suscribir(client, PARAMETRICA)
    await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)
    await procesador.procesar_pendientes()

    # Entrega duplicada (al menos una vez): el evento vuelve a quedar RECIBIDO.
    async with factory() as session:
        modelo = await session.scalar(select(EventoExternoModel))
        modelo.estado = "RECIBIDO"
        await session.commit()
    await procesador.procesar_pendientes()

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(SiniestroModel)) == 1
        assert await session.scalar(select(func.count()).select_from(IndemnizacionModel)) == 1
        assert await session.scalar(select(func.count()).select_from(EventoOutboxModel)) == 2


async def test_evento_sin_polizas_suscritas_no_genera_siniestros(entorno):
    client, factory, procesador, _ = entorno
    await client.post(f"{BASE}/eventos-parametricos", json=_evento(zona="CALI"), headers=FUENTE)

    await procesador.procesar_pendientes()

    [evento] = await _filas(factory, EventoExternoModel)
    assert (evento.estado, evento.resultado) == ("PROCESADO", [])
    assert await _filas(factory, SiniestroModel) == []


async def test_polizas_caido_reintenta_y_luego_queda_fallido(entorno):
    client, factory, procesador, polizas = entorno
    await _suscribir(client, PARAMETRICA)
    await client.post(f"{BASE}/eventos-parametricos", json=_evento(), headers=FUENTE)
    polizas.caido = True

    await procesador.procesar_pendientes()
    [evento] = await _filas(factory, EventoExternoModel)
    assert (evento.estado, evento.intentos) == ("RECIBIDO", 1)
    assert evento.ultimo_error.startswith("PolizasNoDisponibles")
    assert await _filas(factory, SiniestroModel) == []  # nada a medias

    for _ in range(2):
        await procesador.procesar_pendientes()
    [evento] = await _filas(factory, EventoExternoModel)
    assert (evento.estado, evento.intentos) == ("FALLIDO", 3)


async def test_evento_que_no_se_puede_interpretar_queda_descartado(entorno):
    _, factory, procesador, _ = entorno
    async with factory() as session:
        session.add(EventoExternoModel(
            event_id="ROTO-1", fuente="IDEAM", tipo="LLUVIA", checksum="x", ocurrido_en=AHORA, recibido_en=AHORA,
            payload_referencia="x", estado="RECIBIDO", intentos=0, datos={"zona": "BOGOTA"},
        ))
        await session.commit()

    await procesador.procesar_pendientes()

    [evento] = await _filas(factory, EventoExternoModel)
    assert (evento.estado, evento.intentos) == ("DESCARTADO", 1)
    assert "precipitacion_mm" in evento.ultimo_error
