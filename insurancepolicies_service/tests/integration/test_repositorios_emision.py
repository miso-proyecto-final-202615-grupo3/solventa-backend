import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from emision_fakes import (
    AHORA,
    CLIENTE_ID,
    COTIZACION_ID,
    contrato_de,
    firma,
    poliza_emitida,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.certificados.entities import EstadoGeneracion, GeneracionCertificado
from src.domain.certificados.repositories import GeneracionEnCursoDuplicadaError
from src.domain.eventos.entities import EstadoEvento, EventoOutbox
from src.domain.firmas.entities import EstadoFirma
from src.domain.polizas.entities import EstadoCertificado, Poliza, PolizaCobertura
from src.domain.polizas.repositories import PolizaDuplicadaError
from src.infrastructure.persistence.evento_outbox_repository_impl import (
    SqlAlchemyEventoOutboxRepository,
)
from src.infrastructure.persistence.firma_digital_repository_impl import (
    SqlAlchemyFirmaDigitalRepository,
)
from src.infrastructure.persistence.generacion_certificado_repository_impl import (
    SqlAlchemyGeneracionCertificadoRepository,
)
from src.infrastructure.persistence.models import (
    EventoOutboxModel,
    GeneracionCertificadoModel,
    PolizaContratoModel,
    PolizaModel,
)
from src.infrastructure.persistence.poliza_repository_impl import SqlAlchemyPolizaRepository


def nueva_poliza(**cambios) -> Poliza:
    poliza = poliza_emitida(
        cotizacion_id=cambios.pop("cotizacion_id", uuid.uuid4()),
        numero=cambios.pop("numero", f"POL-{uuid.uuid4().hex[:8]}"),
        **cambios,
    )
    poliza.coberturas = [
        PolizaCobertura(
            poliza_id=poliza.poliza_id,
            cobertura_id=uuid.uuid4(),
            limite_asegurado=Decimal("200000000.00"),
            deducible=Decimal("0.00"),
            prima=Decimal("1000000.25"),
        ),
        PolizaCobertura(
            poliza_id=poliza.poliza_id,
            cobertura_id=uuid.uuid4(),
            limite_asegurado=Decimal("50000000.00"),
            deducible=Decimal("100000.00"),
            prima=Decimal("416099.75"),
        ),
    ]
    return poliza


# --- pólizas ---------------------------------------------------------------------------------


async def test_guarda_y_recupera_los_campos_de_emision_y_certificado(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = nueva_poliza()

    await repo.guardar(poliza)
    await db_session.commit()
    db_session.expunge_all()

    encontrada = await repo.obtener_por_id(poliza.poliza_id)
    assert encontrada is not None
    assert encontrada.titular_nombre == "María Fernanda Rodríguez Castañeda"
    assert encontrada.estado_certificado == EstadoCertificado.PENDIENTE
    assert encontrada.ruta_certificado is None
    assert encontrada.ramo == "VIDA" and encontrada.estado == "EMITIDA"
    assert encontrada.prima_total == Decimal("1416100.00")


async def test_las_fechas_se_devuelven_con_zona_horaria(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = nueva_poliza()
    await repo.guardar(poliza)
    await db_session.commit()
    db_session.expunge_all()

    encontrada = await repo.obtener_por_id(poliza.poliza_id)

    assert encontrada.vigencia_desde == poliza.vigencia_desde
    assert encontrada.vigencia_desde.tzinfo is not None
    assert encontrada.vigencia_hasta.tzinfo is not None and encontrada.emitida_en.tzinfo is not None


async def test_obtiene_la_poliza_por_cotizacion(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = nueva_poliza(cotizacion_id=COTIZACION_ID)
    await repo.guardar(poliza)
    await repo.guardar(nueva_poliza())

    encontrada = await repo.obtener_por_cotizacion(COTIZACION_ID)

    assert encontrada is not None and encontrada.poliza_id == poliza.poliza_id
    assert len(encontrada.coberturas) == 2
    assert await repo.obtener_por_cotizacion(uuid.uuid4()) is None


async def test_no_permite_dos_polizas_para_la_misma_cotizacion(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    await repo.guardar(nueva_poliza(cotizacion_id=COTIZACION_ID))
    await db_session.commit()

    with pytest.raises(PolizaDuplicadaError):
        await repo.guardar(nueva_poliza(cotizacion_id=COTIZACION_ID))
    await db_session.rollback()

    assert len((await db_session.execute(PolizaModel.__table__.select())).all()) == 1


async def test_un_error_al_guardar_coberturas_tambien_se_informa_como_duplicado(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = nueva_poliza()
    poliza.coberturas[1].cobertura_id = poliza.coberturas[0].cobertura_id  # UNIQUE(poliza, cobertura)

    with pytest.raises(PolizaDuplicadaError):
        await repo.guardar(poliza)


async def test_guarda_y_lee_el_contrato(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = nueva_poliza()
    await repo.guardar(poliza)
    contrato = contrato_de(poliza)

    await repo.guardar_contrato(contrato)
    await db_session.commit()
    db_session.expunge_all()

    leido = await repo.obtener_contrato(poliza.poliza_id)
    assert leido is not None and leido.datos == contrato.datos
    assert leido.datos["coberturas"][0]["limite_asegurado"] == "200000000.00"
    assert await repo.obtener_contrato(uuid.uuid4()) is None


async def test_actualiza_el_estado_y_la_ruta_del_certificado(db_session: AsyncSession):
    repo = SqlAlchemyPolizaRepository(db_session)
    poliza = nueva_poliza()
    await repo.guardar(poliza)
    await db_session.commit()
    previa = await repo.obtener_por_id(poliza.poliza_id)
    assert previa.estado_certificado == EstadoCertificado.PENDIENTE

    await repo.actualizar_certificado(poliza.poliza_id, EstadoCertificado.GENERADO, "certificados-poliza/x/y/certificado-poliza.pdf")
    await db_session.commit()

    actual = await repo.obtener_por_id(poliza.poliza_id)
    assert actual.estado_certificado == EstadoCertificado.GENERADO
    assert actual.ruta_certificado == "certificados-poliza/x/y/certificado-poliza.pdf"


def test_el_modelo_tiene_los_campos_del_certificado_y_el_indice_unico_por_cotizacion():
    columnas = PolizaModel.__table__.c
    assert columnas.estado_certificado.default.arg == "PENDIENTE"
    assert columnas.estado_certificado.server_default.arg == "PENDIENTE"
    assert columnas.ruta_certificado.nullable and not columnas.estado_certificado.nullable
    indices = {i.name: i for i in PolizaModel.__table__.indexes}
    assert indices["uq_poliza_cotizacion_id"].unique
    assert [c.name for c in indices["uq_poliza_cotizacion_id"].columns] == ["cotizacion_id"]
    assert {c.name for c in PolizaContratoModel.__table__.primary_key} == {"poliza_id"}


# --- firmas ----------------------------------------------------------------------------------


async def test_vincula_la_firma_capturada_a_la_poliza(db_session: AsyncSession):
    polizas = SqlAlchemyPolizaRepository(db_session)
    firmas = SqlAlchemyFirmaDigitalRepository(db_session)
    poliza = nueva_poliza(cotizacion_id=COTIZACION_ID)
    await polizas.guardar(poliza)
    capturada = firma()
    await firmas.crear(capturada)
    await db_session.commit()

    assert await firmas.vincular_a_poliza(capturada.firma_id, poliza.poliza_id) is True
    await db_session.commit()

    vinculada = await firmas.obtener_por_poliza(poliza.poliza_id)
    assert vinculada is not None and vinculada.firma_id == capturada.firma_id
    assert vinculada.estado == EstadoFirma.VINCULADA and vinculada.poliza_id == poliza.poliza_id
    activa = await firmas.obtener_activa_por_cotizacion(COTIZACION_ID)
    assert activa.firma_id == capturada.firma_id and activa.estado == EstadoFirma.VINCULADA


async def test_solo_una_firma_capturada_se_puede_vincular(db_session: AsyncSession):
    polizas = SqlAlchemyPolizaRepository(db_session)
    firmas = SqlAlchemyFirmaDigitalRepository(db_session)
    poliza = nueva_poliza(cotizacion_id=COTIZACION_ID)
    await polizas.guardar(poliza)
    capturada = firma()
    await firmas.crear(capturada)
    assert await firmas.vincular_a_poliza(capturada.firma_id, poliza.poliza_id) is True

    assert await firmas.vincular_a_poliza(capturada.firma_id, poliza.poliza_id) is False
    assert await firmas.vincular_a_poliza(uuid.uuid4(), poliza.poliza_id) is False
    assert await firmas.obtener_por_poliza(uuid.uuid4()) is None


async def test_una_firma_reemplazada_no_se_vincula(db_session: AsyncSession):
    polizas = SqlAlchemyPolizaRepository(db_session)
    firmas = SqlAlchemyFirmaDigitalRepository(db_session)
    poliza = nueva_poliza(cotizacion_id=COTIZACION_ID)
    await polizas.guardar(poliza)
    capturada = firma()
    await firmas.crear(capturada)
    await firmas.reemplazar_capturada(COTIZACION_ID)

    assert await firmas.vincular_a_poliza(capturada.firma_id, poliza.poliza_id) is False
    assert await firmas.obtener_por_poliza(poliza.poliza_id) is None


# --- generaciones de certificado ---------------------------------------------------------------


def nueva_generacion(poliza_id: uuid.UUID, minutos: int = 0, **cambios) -> GeneracionCertificado:
    return GeneracionCertificado(
        poliza_id=poliza_id,
        cliente_id=CLIENTE_ID,
        plantilla="certificado_poliza.html",
        datos_plantilla={"poliza": {"numero": "POL-1"}, "total": "1416100.00"},
        iniciada_en=AHORA + timedelta(minutes=minutos),
        correlation_id="corr-1",
        **cambios,
    )


async def poliza_guardada(db_session: AsyncSession) -> Poliza:
    poliza = nueva_poliza()
    await SqlAlchemyPolizaRepository(db_session).guardar(poliza)
    return poliza


async def test_guarda_la_generacion_con_sus_datos_json(db_session: AsyncSession):
    poliza = await poliza_guardada(db_session)
    repo = SqlAlchemyGeneracionCertificadoRepository(db_session)
    generacion = nueva_generacion(poliza.poliza_id)

    await repo.crear(generacion)
    await db_session.commit()
    db_session.expunge_all()

    leida = await repo.obtener_en_proceso(poliza.poliza_id)
    assert leida is not None and leida.generacion_id == generacion.generacion_id
    assert leida.estado == EstadoGeneracion.EN_PROCESO and leida.finalizada_en is None
    assert leida.datos_plantilla == {"poliza": {"numero": "POL-1"}, "total": "1416100.00"}
    assert leida.plantilla == "certificado_poliza.html" and leida.correlation_id == "corr-1"
    assert leida.iniciada_en == AHORA and leida.iniciada_en.tzinfo is not None


async def test_solo_puede_haber_una_generacion_en_proceso_por_poliza(db_session: AsyncSession):
    poliza = await poliza_guardada(db_session)
    otra = await poliza_guardada(db_session)
    repo = SqlAlchemyGeneracionCertificadoRepository(db_session)
    await repo.crear(nueva_generacion(poliza.poliza_id))
    await db_session.commit()

    with pytest.raises(GeneracionEnCursoDuplicadaError):
        await repo.crear(nueva_generacion(poliza.poliza_id))
    await db_session.rollback()

    await repo.crear(nueva_generacion(otra.poliza_id))  # otra póliza sí puede


async def test_los_intentos_cerrados_no_bloquean_uno_nuevo(db_session: AsyncSession):
    poliza = await poliza_guardada(db_session)
    repo = SqlAlchemyGeneracionCertificadoRepository(db_session)
    fallida = nueva_generacion(poliza.poliza_id, estado=EstadoGeneracion.FALLIDO)
    generada = nueva_generacion(poliza.poliza_id, estado=EstadoGeneracion.GENERADO)

    await repo.crear(fallida)
    await repo.crear(generada)
    await repo.crear(nueva_generacion(poliza.poliza_id, minutos=5))

    assert (await repo.obtener_en_proceso(poliza.poliza_id)) is not None


async def test_actualizar_cierra_la_generacion_una_sola_vez(db_session: AsyncSession):
    poliza = await poliza_guardada(db_session)
    repo = SqlAlchemyGeneracionCertificadoRepository(db_session)
    generacion = nueva_generacion(poliza.poliza_id)
    await repo.crear(generacion)
    generacion.estado = EstadoGeneracion.GENERADO
    generacion.finalizada_en = AHORA + timedelta(seconds=3)
    generacion.ruta_certificado = "certificados-poliza/c/p/certificado-poliza.pdf"

    assert await repo.actualizar(generacion) is True
    await db_session.commit()
    db_session.expunge_all()

    cerrada = await repo.obtener_ultima(poliza.poliza_id)
    assert cerrada.estado == EstadoGeneracion.GENERADO
    assert cerrada.finalizada_en == AHORA + timedelta(seconds=3)
    assert cerrada.ruta_certificado == "certificados-poliza/c/p/certificado-poliza.pdf"
    assert await repo.obtener_en_proceso(poliza.poliza_id) is None

    # ya no está EN_PROCESO: otro cierre (p. ej. el de un proceso rezagado) no la modifica
    generacion.estado = EstadoGeneracion.FALLIDO
    assert await repo.actualizar(generacion) is False
    assert (await repo.obtener_ultima(poliza.poliza_id)).estado == EstadoGeneracion.GENERADO


async def test_obtener_ultima_devuelve_el_intento_mas_reciente(db_session: AsyncSession):
    poliza = await poliza_guardada(db_session)
    repo = SqlAlchemyGeneracionCertificadoRepository(db_session)
    await repo.crear(nueva_generacion(poliza.poliza_id, minutos=0, estado=EstadoGeneracion.FALLIDO))
    reciente = nueva_generacion(poliza.poliza_id, minutos=10, estado=EstadoGeneracion.GENERADO)
    await repo.crear(reciente)
    await repo.crear(nueva_generacion(poliza.poliza_id, minutos=5, estado=EstadoGeneracion.FALLIDO))

    ultima = await repo.obtener_ultima(poliza.poliza_id)

    assert ultima.generacion_id == reciente.generacion_id
    assert await repo.obtener_ultima(uuid.uuid4()) is None


def test_el_modelo_de_auditoria_guarda_lo_pedido():
    columnas = {c.name for c in GeneracionCertificadoModel.__table__.columns}

    assert {
        "poliza_id",
        "estado",
        "iniciada_en",
        "finalizada_en",
        "ruta_certificado",
        "plantilla",
        "datos_plantilla",
    } <= columnas
    assert not columnas & {"firma_base64", "imagen", "contenido"}


# --- outbox ----------------------------------------------------------------------------------


def nuevo_evento(minutos: int = 0) -> EventoOutbox:
    return EventoOutbox(
        tipo="PolizaEmitida",
        agregado_id=uuid.uuid4(),
        payload={"datos": {"n": minutos}},
        creado_en=AHORA + timedelta(minutes=minutos),
    )


async def test_el_evento_forma_parte_de_la_transaccion(db_session: AsyncSession):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    await repo.agregar(nuevo_evento())

    await db_session.rollback()

    assert await repo.obtener_pendientes(10) == []


async def test_obtiene_pendientes_en_orden_de_creacion_y_respeta_el_limite(db_session: AsyncSession):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    segundo, primero, tercero = nuevo_evento(2), nuevo_evento(1), nuevo_evento(3)
    for evento in (segundo, primero, tercero):
        await repo.agregar(evento)
    await db_session.commit()

    pendientes = await repo.obtener_pendientes(2)

    assert [e.evento_id for e in pendientes] == [primero.evento_id, segundo.evento_id]
    assert pendientes[0].payload == primero.payload and pendientes[0].estado == EstadoEvento.PENDIENTE


async def test_marcar_publicado_y_registrar_fallo(db_session: AsyncSession):
    repo = SqlAlchemyEventoOutboxRepository(db_session)
    publicado, fallido = nuevo_evento(1), nuevo_evento(2)
    await repo.agregar(publicado)
    await repo.agregar(fallido)
    await repo.registrar_fallo(fallido.evento_id, "x" * 600)
    await repo.marcar_publicado(publicado.evento_id, AHORA)
    await db_session.commit()

    pendientes = await repo.obtener_pendientes(10)

    assert [e.evento_id for e in pendientes] == [fallido.evento_id]
    assert (pendientes[0].intentos, len(pendientes[0].ultimo_error)) == (1, 500)
    fila = (
        await db_session.execute(
            EventoOutboxModel.__table__.select().where(EventoOutboxModel.evento_id == publicado.evento_id)
        )
    ).one()
    assert (fila.estado, fila.intentos, fila.ultimo_error) == ("PUBLICADO", 1, None)
    assert fila.publicado_en is not None
