import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from src.application.use_cases.consultar_siniestro_use_case import ConsultarSiniestroUseCase
from src.application.use_cases.listar_polizas_elegibles_use_case import ListarPolizasElegiblesUseCase
from src.application.use_cases.reportar_siniestro_use_case import ReporteSiniestroCmd, ReportarSiniestroUseCase
from src.domain.siniestros.errores import (
    FechaFueraDeVigencia,
    FechaInvalida,
    IdempotenciaConflicto,
    PolizaNoEncontrada,
    PolizaNoVigente,
    ServicioNoDisponible,
    SiniestroNoEncontrado,
    TipoNoPermitido,
)
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import (
    SqlAlchemyCatalogoTiposSiniestro,
    invalidar_cache,
)
from src.infrastructure.persistence.models import SiniestroModel
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.infrastructure.persistence.siniestros_repository_impl import SqlAlchemySiniestroRepository
from tests.fakes import AHORA, CLIENTE, OTRO_CLIENTE, PolizasFalsas, poliza

BOGOTA = timezone(timedelta(hours=-5))


@pytest.fixture
async def catalogo(db_session):
    invalidar_cache()
    await sembrar_tipos_siniestro(db_session)
    await db_session.commit()
    yield SqlAlchemyCatalogoTiposSiniestro(db_session)
    invalidar_cache()


def _reportar(db_session, catalogo, polizas) -> ReportarSiniestroUseCase:
    return ReportarSiniestroUseCase(
        db_session, SqlAlchemySiniestroRepository(db_session), polizas, catalogo, lambda: AHORA, ["VIGENTE"]
    )


def _cmd(**cambios) -> ReporteSiniestroCmd:
    datos = {
        "cliente_id": CLIENTE,
        "clave_idempotencia": str(uuid.uuid4()),
        "poliza_id": poliza().poliza_id,
        "tipo": "GASTO_MEDICO",
        "descripcion": "Me atendieron en urgencias durante el viaje.",
        "ocurrido_en": datetime(2026, 11, 10, 14, 30, tzinfo=BOGOTA),
    }
    datos.update(cambios)
    return ReporteSiniestroCmd(**datos)


async def _total(db_session) -> int:
    return await db_session.scalar(select(func.count()).select_from(SiniestroModel))


# --- Pólizas elegibles ---------------------------------------------------------------------------

async def test_elegibles_filtra_estado_vigencia_dueno_y_productos_sin_catalogo(catalogo):
    vigente = poliza()
    dispositivos = poliza(
        poliza_id=uuid.uuid4(), numero="SLV-2026-09120", producto_codigo="PROTECCION_DISPOSITIVOS",
        vigencia_hasta=date(2027, 6, 1),
    )
    polizas = PolizasFalsas(
        vigente,
        dispositivos,
        poliza(poliza_id=uuid.uuid4(), estado="VENCIDA"),
        poliza(poliza_id=uuid.uuid4(), vigencia_hasta=date(2026, 11, 9)),
        poliza(poliza_id=uuid.uuid4(), producto_codigo="MICROSEGURO_VIDA"),
        poliza(poliza_id=uuid.uuid4(), cliente_id=OTRO_CLIENTE),
    )
    use_case = ListarPolizasElegiblesUseCase(polizas, catalogo, lambda: AHORA, ["VIGENTE"])

    elegibles = await use_case.ejecutar(CLIENTE, "corr-1")

    assert [e.poliza.numero for e in elegibles] == ["SLV-2026-09120", "SLV-2026-08341"]
    assert [t.codigo for t in elegibles[1].tipos] == ["GASTO_MEDICO", "EQUIPAJE", "CANCELACION_VIAJE"]
    assert polizas.llamadas == [("listar", "corr-1")]


async def test_elegibles_sin_polizas_es_lista_vacia(catalogo):
    use_case = ListarPolizasElegiblesUseCase(PolizasFalsas(), catalogo, lambda: AHORA, ["VIGENTE"])

    assert await use_case.ejecutar(CLIENTE, "c") == []


async def test_elegibles_con_polizas_caido_es_servicio_no_disponible(catalogo):
    use_case = ListarPolizasElegiblesUseCase(PolizasFalsas(caido=True), catalogo, lambda: AHORA, ["VIGENTE"])

    with pytest.raises(ServicioNoDisponible):
        await use_case.ejecutar(CLIENTE, "c")


# --- Reportar ------------------------------------------------------------------------------------

async def test_reporta_el_siniestro_en_estado_reportado(db_session, catalogo):
    cmd = _cmd()

    resultado = await _reportar(db_session, catalogo, PolizasFalsas(poliza())).ejecutar(cmd, "corr")

    s = resultado.siniestro
    assert resultado.repetido is False
    assert s.estado == "REPORTADO" and s.canal == "MOVIL"
    assert s.numero == f"SIN-2026-{s.siniestro_id.hex[:8].upper()}"
    assert s.cliente_id == CLIENTE
    assert s.poliza_numero == "SLV-2026-08341" and s.producto_codigo == "SEGURO_VIAJE"
    assert s.ocurrido_en == datetime(2026, 11, 10, 19, 30, tzinfo=timezone.utc)
    assert s.reportado_en == AHORA
    assert await _total(db_session) == 1


async def test_reintento_con_la_misma_clave_devuelve_el_mismo_siniestro(db_session, catalogo):
    use_case = _reportar(db_session, catalogo, PolizasFalsas(poliza()))
    cmd = _cmd()

    primero = await use_case.ejecutar(cmd, "c")
    segundo = await use_case.ejecutar(cmd, "c")

    assert segundo.repetido is True
    assert segundo.siniestro.siniestro_id == primero.siniestro.siniestro_id
    assert await _total(db_session) == 1


@pytest.mark.parametrize(
    "cambios",
    [{"descripcion": "Otra descripción distinta del evento."}, {"cliente_id": OTRO_CLIENTE}],
)
async def test_misma_clave_con_otros_datos_es_conflicto(db_session, catalogo, cambios):
    use_case = _reportar(db_session, catalogo, PolizasFalsas(poliza()))
    cmd = _cmd()
    await use_case.ejecutar(cmd, "c")

    with pytest.raises(IdempotenciaConflicto):
        await use_case.ejecutar(_cmd(clave_idempotencia=cmd.clave_idempotencia, **cambios), "c")


async def test_poliza_ajena_o_inexistente_es_no_encontrada(db_session, catalogo):
    use_case = _reportar(db_session, catalogo, PolizasFalsas(poliza(cliente_id=OTRO_CLIENTE)))

    with pytest.raises(PolizaNoEncontrada):
        await use_case.ejecutar(_cmd(), "c")
    with pytest.raises(PolizaNoEncontrada):
        await use_case.ejecutar(_cmd(poliza_id=uuid.uuid4()), "c")


async def test_poliza_no_vigente(db_session, catalogo):
    with pytest.raises(PolizaNoVigente):
        await _reportar(db_session, catalogo, PolizasFalsas(poliza(estado="CANCELADA"))).ejecutar(_cmd(), "c")


@pytest.mark.parametrize(
    ("ocurrido", "valido"),
    [
        (datetime(2026, 3, 12, 0, 1, tzinfo=BOGOTA), True),
        (datetime(2026, 3, 11, 23, 59, tzinfo=BOGOTA), False),
        (datetime(2025, 1, 1, 10, 0, tzinfo=BOGOTA), False),
    ],
)
async def test_bordes_de_vigencia(db_session, catalogo, ocurrido, valido):
    use_case = _reportar(db_session, catalogo, PolizasFalsas(poliza()))

    if valido:
        assert (await use_case.ejecutar(_cmd(ocurrido_en=ocurrido), "c")).siniestro.numero
    else:
        with pytest.raises(FechaFueraDeVigencia):
            await use_case.ejecutar(_cmd(ocurrido_en=ocurrido), "c")


async def test_fecha_futura_con_tolerancia_de_cinco_minutos(db_session, catalogo):
    use_case = _reportar(db_session, catalogo, PolizasFalsas(poliza()))

    await use_case.ejecutar(_cmd(ocurrido_en=AHORA + timedelta(minutes=4)), "c")
    with pytest.raises(FechaInvalida):
        await use_case.ejecutar(_cmd(ocurrido_en=AHORA + timedelta(minutes=6)), "c")


async def test_tipo_que_no_es_del_producto(db_session, catalogo):
    with pytest.raises(TipoNoPermitido):
        await _reportar(db_session, catalogo, PolizasFalsas(poliza())).ejecutar(_cmd(tipo="ROBO"), "c")


async def test_polizas_caido_no_guarda_nada(db_session, catalogo):
    with pytest.raises(ServicioNoDisponible):
        await _reportar(db_session, catalogo, PolizasFalsas(poliza(), caido=True)).ejecutar(_cmd(), "c")

    assert await _total(db_session) == 0


# --- Consultar -----------------------------------------------------------------------------------

async def test_consulta_solo_los_siniestros_del_cliente(db_session, catalogo):
    creado = (await _reportar(db_session, catalogo, PolizasFalsas(poliza())).ejecutar(_cmd(), "c")).siniestro
    consultar = ConsultarSiniestroUseCase(SqlAlchemySiniestroRepository(db_session))

    assert (await consultar.ejecutar(creado.siniestro_id, CLIENTE)).numero == creado.numero
    with pytest.raises(SiniestroNoEncontrado):
        await consultar.ejecutar(creado.siniestro_id, OTRO_CLIENTE)
    with pytest.raises(SiniestroNoEncontrado):
        await consultar.ejecutar(uuid.uuid4(), CLIENTE)
