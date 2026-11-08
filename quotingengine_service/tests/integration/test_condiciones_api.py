import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.infrastructure.persistence.models import (
    CondicionesCotizacionModel,
    CotizacionModel,
    CotizacionCoberturaModel,
    AuditoriaDecisionModel,
    CoberturaModel,
    DecisionCondicionesModel,
    ProductoSeguroModel,
)
from src.infrastructure.persistence.seed import (
    CONDICIONES_GENERALES,
    VERSION_CONDICIONES,
    sembrar_catalogo,
)

BASE = f"{settings.API_PREFIX}/cotizaciones"


@pytest.fixture(autouse=True)
async def catalogo(db_session: AsyncSession):
    await sembrar_catalogo(db_session)


async def crear_cotizacion(client: AsyncClient) -> dict:
    response = await client.post(BASE, json={
        "cliente_id": str(uuid.uuid4()),
        "producto_codigo": "SEGURO_VIAJE",
        "parametros": {"valor_viaje": 1000000},
    })
    assert response.status_code == 201
    return response.json()


async def test_consulta_snapshot_inmutable(api_client: AsyncClient, db_session: AsyncSession):
    cotizacion = await crear_cotizacion(api_client)
    url = f"{BASE}/{cotizacion['cotizacion_id']}/condiciones"
    response = await api_client.get(url)
    assert response.status_code == 200
    condiciones = response.json()
    particulares = condiciones["condiciones_particulares"]
    assert condiciones["version_condiciones_generales"] == VERSION_CONDICIONES
    assert condiciones["condiciones_generales"]
    assert condiciones["condiciones_generales"] == CONDICIONES_GENERALES["SEGURO_VIAJE"]
    assert set(particulares) == {
        "prima_total", "moneda", "vigencia_propuesta", "coberturas"
    }
    assert particulares["prima_total"] == cotizacion["prima_total"]
    assert particulares["moneda"] == cotizacion["moneda"]
    vigencia = particulares["vigencia_propuesta"]
    assert set(vigencia) == {"desde", "hasta"}
    creada_en = datetime.fromisoformat(cotizacion["creada_en"])
    if creada_en.tzinfo is None:
        creada_en = creada_en.replace(tzinfo=timezone.utc)
    assert datetime.fromisoformat(vigencia["desde"]) == creada_en
    assert datetime.fromisoformat(vigencia["hasta"]) == creada_en.replace(year=creada_en.year + 1)
    assert len(particulares["coberturas"]) == len(cotizacion["coberturas"]) == 3
    campos_monetarios = {"prima", "limite_asegurado", "deducible"}
    assert all(set(cobertura) == campos_monetarios for cobertura in particulares["coberturas"])
    assert sorted(tuple(c[k] for k in sorted(campos_monetarios)) for c in particulares["coberturas"]) == sorted(
        tuple(c[k] for k in sorted(campos_monetarios)) for c in cotizacion["coberturas"]
    )
    guardadas = (await db_session.execute(select(CondicionesCotizacionModel))).scalar_one()
    assert guardadas.condiciones_particulares == particulares

    await db_session.execute(
        update(ProductoSeguroModel).where(ProductoSeguroModel.codigo == "SEGURO_VIAJE")
        .values(condiciones_generales="Texto modificado", version_condiciones_generales="2.0")
    )
    await db_session.execute(
        update(CoberturaModel)
        .where(CoberturaModel.cobertura_id == uuid.UUID(cotizacion["coberturas"][0]["cobertura_id"]))
        .values(nombre="Cobertura modificada", limite_asegurado=1, estado="INACTIVA")
    )
    await db_session.commit()
    assert (await api_client.get(url)).json() == condiciones


async def test_consulta_condiciones_solo_declara_cotizacion_id(api_client: AsyncClient):
    schema = (await api_client.get("/openapi.json")).json()
    operacion = schema["paths"][f"{BASE}/{{cotizacion_id}}/condiciones"]["get"]
    assert [(p["name"], p["in"]) for p in operacion["parameters"]] == [
        ("cotizacion_id", "path")
    ]


@pytest.mark.parametrize("decision", ["ACEPTADA", "RECHAZADA"])
async def test_decision_queda_auditada(api_client: AsyncClient, db_session: AsyncSession, decision):
    cotizacion = await crear_cotizacion(api_client)
    url = f"{BASE}/{cotizacion['cotizacion_id']}/condiciones"
    condiciones = (await api_client.get(url)).json()
    payload = {
        "condiciones_cotizacion_id": condiciones["condiciones_cotizacion_id"],
        "decision": decision,
    }
    response = await api_client.post(f"{url}/decisiones", json=payload)
    assert response.status_code == 201
    assert set(response.json()) == {
        "decision_condiciones_id",
        "condiciones_cotizacion_id",
        "cliente_id",
        "version_condiciones_generales",
        "decision",
        "decidida_en",
    }
    assert response.json()["decision"] == decision
    assert response.json()["cliente_id"] == cotizacion["cliente_id"]
    assert response.json()["condiciones_cotizacion_id"] == condiciones["condiciones_cotizacion_id"]
    assert response.json()["version_condiciones_generales"] == condiciones["version_condiciones_generales"]
    evento = (await db_session.execute(select(DecisionCondicionesModel))).scalar_one()
    assert str(evento.cliente_id) == cotizacion["cliente_id"]
    assert str(evento.condiciones_cotizacion_id) == condiciones["condiciones_cotizacion_id"]
    assert evento.decision == decision
    assert evento.decidida_en is not None
    consulta = (await api_client.get(url)).json()
    assert consulta["ultima_decision"]["decision_condiciones_id"] == response.json()["decision_condiciones_id"]
    assert consulta["ultima_decision"]["decision"] == decision
    assert set(consulta["ultima_decision"]) == set(response.json())


async def test_esquema_decision_no_declara_siguiente_paso(api_client: AsyncClient):
    schema = (await api_client.get("/openapi.json")).json()
    propiedades = schema["components"]["schemas"]["DecisionResponse"]["properties"]
    assert "siguiente_paso" not in propiedades


async def test_esquema_solicitud_decision_no_declara_cliente(api_client: AsyncClient):
    schema = (await api_client.get("/openapi.json")).json()
    solicitud = schema["components"]["schemas"]["DecisionRequest"]
    assert set(solicitud["properties"]) == {"condiciones_cotizacion_id", "decision"}
    assert set(solicitud["required"]) == {"condiciones_cotizacion_id", "decision"}


async def test_validacion_snapshot_y_decision(api_client: AsyncClient, db_session: AsyncSession):
    cotizacion = await crear_cotizacion(api_client)
    url = f"{BASE}/{cotizacion['cotizacion_id']}/condiciones"
    assert (await api_client.get(f"{BASE}/{uuid.uuid4()}/condiciones")).status_code == 404
    assert (await api_client.get(f"{BASE}/invalida/condiciones")).status_code == 422
    condiciones = (await api_client.get(url)).json()
    payload = {"condiciones_cotizacion_id": condiciones["condiciones_cotizacion_id"], "decision": "ACEPTADA"}
    assert (await api_client.post(f"{url}/decisiones", json={**payload, "cliente_id": str(uuid.uuid4())})).status_code == 422
    assert (await api_client.post(f"{url}/decisiones", json={**payload, "cliente_id": cotizacion["cliente_id"]})).status_code == 422
    assert (await api_client.post(f"{BASE}/{uuid.uuid4()}/condiciones/decisiones", json=payload)).status_code == 404
    assert (await api_client.post(f"{url}/decisiones", json={**payload, "condiciones_cotizacion_id": str(uuid.uuid4())})).status_code == 409
    assert (await api_client.post(f"{url}/decisiones", json={**payload, "decision": "OTRA"})).status_code == 422
    await db_session.execute(update(CotizacionModel).where(
        CotizacionModel.cotizacion_id == uuid.UUID(cotizacion["cotizacion_id"])
    ).values(expira_en=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db_session.commit()
    assert (await api_client.post(f"{url}/decisiones", json=payload)).status_code == 409
    assert (await db_session.execute(select(DecisionCondicionesModel))).scalars().all() == []


async def test_decision_rechaza_condiciones_de_otra_cotizacion(api_client: AsyncClient, db_session: AsyncSession):
    primera = await crear_cotizacion(api_client)
    segunda = await crear_cotizacion(api_client)
    url_segunda = f"{BASE}/{segunda['cotizacion_id']}/condiciones"
    condiciones_segunda = (await api_client.get(url_segunda)).json()
    response = await api_client.post(
        f"{BASE}/{primera['cotizacion_id']}/condiciones/decisiones",
        json={
            "condiciones_cotizacion_id": condiciones_segunda["condiciones_cotizacion_id"],
            "decision": "ACEPTADA",
        },
    )
    assert response.status_code == 409
    assert (await db_session.execute(select(DecisionCondicionesModel))).scalars().all() == []


async def test_cotizacion_anterior_sin_snapshot_no_inventa_condiciones(api_client: AsyncClient, db_session: AsyncSession):
    cotizacion = await crear_cotizacion(api_client)
    condiciones = (await db_session.execute(select(CondicionesCotizacionModel))).scalar_one()
    condiciones_id = str(condiciones.condiciones_cotizacion_id)
    await db_session.delete(condiciones)
    await db_session.commit()
    response = await api_client.get(
        f"{BASE}/{cotizacion['cotizacion_id']}/condiciones",
    )
    assert response.status_code == 404
    decision = await api_client.post(
        f"{BASE}/{cotizacion['cotizacion_id']}/condiciones/decisiones",
        json={"condiciones_cotizacion_id": condiciones_id, "decision": "ACEPTADA"},
    )
    assert decision.status_code == 404


async def test_decisiones_sucesivas_preservan_auditoria(api_client: AsyncClient, db_session: AsyncSession):
    cotizacion = await crear_cotizacion(api_client)
    url = f"{BASE}/{cotizacion['cotizacion_id']}/condiciones"
    condiciones = (await api_client.get(url)).json()
    payload = {
        "condiciones_cotizacion_id": condiciones["condiciones_cotizacion_id"],
        "decision": "ACEPTADA",
    }
    assert (await api_client.post(f"{url}/decisiones", json=payload)).status_code == 201
    assert (await api_client.post(f"{url}/decisiones", json={**payload, "decision": "RECHAZADA"})).status_code == 201
    consulta = (await api_client.get(url)).json()
    assert consulta["ultima_decision"]["decision"] == "RECHAZADA"
    assert "siguiente_paso" not in consulta["ultima_decision"]
    assert len((await db_session.execute(select(DecisionCondicionesModel))).scalars().all()) == 2


async def test_producto_sin_condiciones_no_se_cotiza(api_client: AsyncClient, db_session: AsyncSession):
    await db_session.execute(
        update(ProductoSeguroModel).where(ProductoSeguroModel.codigo == "SEGURO_VIAJE")
        .values(condiciones_generales=None, version_condiciones_generales=None)
    )
    await db_session.commit()
    response = await api_client.post(BASE, json={
        "cliente_id": str(uuid.uuid4()),
        "producto_codigo": "SEGURO_VIAJE",
        "parametros": {"valor_viaje": 1000000},
    })
    assert response.status_code == 503
    assert (await db_session.execute(select(CotizacionModel))).scalars().all() == []


async def test_fallo_al_guardar_snapshot_revierte_cotizacion(api_client: AsyncClient, db_session: AsyncSession, monkeypatch):
    from src.infrastructure.persistence.condiciones_cotizacion_repository_impl import SqlAlchemyCondicionesCotizacionRepository

    async def fallar(self, condiciones):
        raise RuntimeError("error de persistencia")

    monkeypatch.setattr(SqlAlchemyCondicionesCotizacionRepository, "guardar", fallar)
    with pytest.raises(RuntimeError, match="error de persistencia"):
        await crear_cotizacion(api_client)
    for model in (CotizacionModel, CotizacionCoberturaModel, AuditoriaDecisionModel, CondicionesCotizacionModel):
        assert (await db_session.execute(select(model))).scalars().all() == []


async def test_cotizacion_sin_fecha_de_creacion_revierte_transaccion(api_client: AsyncClient, db_session: AsyncSession, monkeypatch):
    from src.infrastructure.persistence.cotizacion_repository_impl import SqlAlchemyCotizacionRepository

    guardar_original = SqlAlchemyCotizacionRepository.guardar

    async def guardar_sin_fecha(self, cotizacion):
        resultado = await guardar_original(self, cotizacion)
        resultado.creada_en = None
        return resultado

    monkeypatch.setattr(SqlAlchemyCotizacionRepository, "guardar", guardar_sin_fecha)
    with pytest.raises(RuntimeError, match="no tiene fecha de creación"):
        await crear_cotizacion(api_client)
    for model in (CotizacionModel, CotizacionCoberturaModel, AuditoriaDecisionModel, CondicionesCotizacionModel):
        assert (await db_session.execute(select(model))).scalars().all() == []


async def test_fallo_al_guardar_decision_revierte_evento(api_client: AsyncClient, db_session: AsyncSession, monkeypatch):
    from src.infrastructure.persistence.decision_condiciones_repository_impl import SqlAlchemyDecisionCondicionesRepository

    cotizacion = await crear_cotizacion(api_client)
    url = f"{BASE}/{cotizacion['cotizacion_id']}/condiciones"
    condiciones = (await api_client.get(url)).json()
    guardar_original = SqlAlchemyDecisionCondicionesRepository.guardar

    async def fallar(self, decision):
        await guardar_original(self, decision)
        raise RuntimeError("error de persistencia")

    monkeypatch.setattr(SqlAlchemyDecisionCondicionesRepository, "guardar", fallar)
    with pytest.raises(RuntimeError, match="error de persistencia"):
        await api_client.post(f"{url}/decisiones", json={
            "condiciones_cotizacion_id": condiciones["condiciones_cotizacion_id"],
            "decision": "ACEPTADA",
        })
    assert (await db_session.execute(select(DecisionCondicionesModel))).scalars().all() == []
