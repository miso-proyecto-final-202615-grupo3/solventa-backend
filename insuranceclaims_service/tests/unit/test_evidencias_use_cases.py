import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.application.use_cases.evidencias_use_cases import (
    ConfirmarCargaEvidenciaUseCase,
    ConsultarDetalleSiniestroUseCase,
    RegistrarUbicacionUseCase,
    SolicitarCargaEvidenciaUseCase,
    SolicitudCargaCmd,
)
from src.domain.siniestros.entities import Siniestro
from src.domain.siniestros.errores import (
    CargaExpirada,
    CargaNoEncontrada,
    EvidenciaNoEncontrada,
    EvidenciaRechazada,
    FechaInvalida,
    IdempotenciaConflicto,
    LimiteEvidencias,
    ServicioNoDisponible,
    SiniestroNoAdmiteEvidencias,
    SiniestroNoEncontrado,
    TipoEvidenciaNoPermitido,
)
from src.domain.siniestros.evidencias import OrigenEvidencia, TipoEvidencia
from src.domain.siniestros.politica_evidencias import PoliticaEvidencias
from src.domain.siniestros.ubicacion import FuenteUbicacion, UbicacionSiniestro
from src.infrastructure.persistence.catalogo_tipos_siniestro_impl import (
    SqlAlchemyCatalogoTiposSiniestro,
    invalidar_cache,
)
from src.infrastructure.persistence.seed_tipos_siniestro import sembrar_tipos_siniestro
from src.infrastructure.persistence.siniestros_repository_impl import (
    SqlAlchemyEvidenciaRepository,
    SqlAlchemySiniestroRepository,
)
from src.infrastructure.storage.memoria import AlmacenEvidenciasEnMemoria
from tests.fakes import CLIENTE, OTRO_CLIENTE

AHORA = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 96
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 88


class Reloj:
    def __init__(self) -> None:
        self.ahora = AHORA

    def __call__(self) -> datetime:
        return self.ahora


@pytest.fixture
async def entorno(db_session):
    invalidar_cache()
    await sembrar_tipos_siniestro(db_session)
    siniestros = SqlAlchemySiniestroRepository(db_session)
    evidencias = SqlAlchemyEvidenciaRepository(db_session)
    siniestro = Siniestro(
        poliza_id=uuid.uuid4(), tipo="EQUIPAJE", estado="REPORTADO", clave_idempotencia=str(uuid.uuid4()),
        ocurrido_en=AHORA, reportado_en=AHORA, cliente_id=CLIENTE, numero="SIN-2026-ABCDEF01", canal="MOVIL",
        producto_codigo="SEGURO_VIAJE", poliza_numero="SLV-2026-08341",
    )
    await siniestros.guardar(siniestro)
    await db_session.commit()
    reloj = Reloj()
    almacen = AlmacenEvidenciasEnMemoria(reloj)
    catalogo = SqlAlchemyCatalogoTiposSiniestro(db_session)
    politica = PoliticaEvidencias()
    yield {
        "session": db_session, "siniestro": siniestro, "almacen": almacen, "reloj": reloj,
        "solicitar": SolicitarCargaEvidenciaUseCase(
            db_session, siniestros, evidencias, catalogo, almacen, politica, reloj, "siniestros/"
        ),
        "confirmar": ConfirmarCargaEvidenciaUseCase(db_session, siniestros, evidencias, almacen, politica, reloj),
        "ubicacion": RegistrarUbicacionUseCase(db_session, siniestros, politica, reloj),
        "detalle": ConsultarDetalleSiniestroUseCase(siniestros, evidencias, reloj),
        "siniestros": siniestros,
    }
    invalidar_cache()


def _cmd(entorno, tipo=TipoEvidencia.FOTO, tamano=len(JPEG), cliente=CLIENTE, **cambios) -> SolicitudCargaCmd:
    datos = dict(
        siniestro_id=entorno["siniestro"].siniestro_id, cliente_id=cliente, tipo=tipo,
        content_type="image/jpeg" if tipo == TipoEvidencia.FOTO else "video/mp4",
        tamano_bytes=tamano, origen=OrigenEvidencia.CAMARA, capturada_en=AHORA,
    )
    datos.update(cambios)
    return SolicitudCargaCmd(**datos)


async def _subir_y_confirmar(entorno, contenido=JPEG, tipo=TipoEvidencia.FOTO, content_type="image/jpeg"):
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno, tipo=tipo, tamano=len(contenido)), "c")
    entorno["almacen"].simular_subida(resultado.evidencia.objeto_clave, contenido, content_type)
    return await entorno["confirmar"].ejecutar(
        entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id, CLIENTE, "c"
    )


async def test_solicitar_crea_pendiente_con_carga_firmada(entorno):
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno), "c")

    evidencia = resultado.evidencia
    assert evidencia.estado == "PENDIENTE"
    assert evidencia.objeto_clave == f"siniestros/{entorno['siniestro'].siniestro_id}/evidencias/{evidencia.evidencia_id}.jpg"
    assert evidencia.expira_en == AHORA + timedelta(minutes=10)
    assert resultado.tamano_max_bytes == 5 * 1024 * 1024
    assert resultado.carga.campos["key"] == evidencia.objeto_clave


async def test_flujo_completo_foto_y_video(entorno):
    foto = await _subir_y_confirmar(entorno)
    video = await _subir_y_confirmar(entorno, MP4, TipoEvidencia.VIDEO, "video/mp4")

    assert (foto.estado, video.estado) == ("CARGADA", "CARGADA")
    detalle = await entorno["detalle"].ejecutar(entorno["siniestro"].siniestro_id, CLIENTE)
    assert [e.tipo for e in detalle.evidencias] == ["FOTO", "VIDEO"]


async def test_confirmar_dos_veces_es_idempotente(entorno):
    primera = await _subir_y_confirmar(entorno)

    segunda = await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, primera.evidencia_id, CLIENTE, "c")

    assert segunda.estado == "CARGADA"


async def test_siniestro_ajeno_es_no_encontrado(entorno):
    with pytest.raises(SiniestroNoEncontrado):
        await entorno["solicitar"].ejecutar(_cmd(entorno, cliente=OTRO_CLIENTE), "c")


async def test_siniestro_que_ya_no_esta_reportado(entorno):
    siniestro = entorno["siniestro"]
    siniestro.estado = "EN_EVALUACION"
    await entorno["siniestros"].actualizar(siniestro)
    await entorno["session"].commit()

    with pytest.raises(SiniestroNoAdmiteEvidencias):
        await entorno["solicitar"].ejecutar(_cmd(entorno), "c")


async def test_limite_de_videos_y_las_vencidas_no_cuentan(entorno):
    await entorno["solicitar"].ejecutar(_cmd(entorno, tipo=TipoEvidencia.VIDEO, tamano=100), "c")
    with pytest.raises(LimiteEvidencias):
        await entorno["solicitar"].ejecutar(_cmd(entorno, tipo=TipoEvidencia.VIDEO, tamano=100), "c")

    entorno["reloj"].ahora = AHORA + timedelta(minutes=31)  # el video pendiente vence
    nueva = await entorno["solicitar"].ejecutar(_cmd(entorno, tipo=TipoEvidencia.VIDEO, tamano=100, capturada_en=AHORA), "c")

    assert nueva.evidencia.estado == "PENDIENTE"


async def test_video_en_un_tipo_sin_video(entorno):
    siniestro = entorno["siniestro"]
    siniestro.tipo = "GASTO_MEDICO"
    await entorno["siniestros"].actualizar(siniestro)
    await entorno["session"].commit()

    with pytest.raises(TipoEvidenciaNoPermitido):
        await entorno["solicitar"].ejecutar(_cmd(entorno, tipo=TipoEvidencia.VIDEO, tamano=100), "c")


async def test_captura_en_el_futuro(entorno):
    with pytest.raises(FechaInvalida):
        await entorno["solicitar"].ejecutar(_cmd(entorno, capturada_en=AHORA + timedelta(minutes=6)), "c")


async def test_almacen_caido_no_deja_evidencia(entorno):
    entorno["almacen"].caido = True

    with pytest.raises(ServicioNoDisponible):
        await entorno["solicitar"].ejecutar(_cmd(entorno), "c")

    detalle = await entorno["detalle"].ejecutar(entorno["siniestro"].siniestro_id, CLIENTE)
    assert detalle.evidencias == []


async def test_confirmar_sin_archivo_vigente_y_vencido(entorno):
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno), "c")
    siniestro_id, evidencia_id = entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id

    with pytest.raises(CargaNoEncontrada):
        await entorno["confirmar"].ejecutar(siniestro_id, evidencia_id, CLIENTE, "c")
    entorno["reloj"].ahora = AHORA + timedelta(minutes=11)
    with pytest.raises(CargaExpirada):
        await entorno["confirmar"].ejecutar(siniestro_id, evidencia_id, CLIENTE, "c")
    with pytest.raises(CargaExpirada):
        await entorno["confirmar"].ejecutar(siniestro_id, evidencia_id, CLIENTE, "c")


@pytest.mark.parametrize(
    ("contenido", "content_type", "declarado"),
    [
        (JPEG, "image/jpeg", len(JPEG) + 1),          # tamaño distinto
        (JPEG, "image/png", len(JPEG)),                # tipo distinto
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 92, "image/jpeg", 100),  # no es JPEG
    ],
)
async def test_archivo_que_no_coincide_se_borra_y_rechaza(entorno, contenido, content_type, declarado):
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno, tamano=declarado), "c")
    clave = resultado.evidencia.objeto_clave
    entorno["almacen"].simular_subida(clave, contenido, content_type)

    with pytest.raises(EvidenciaRechazada):
        await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id, CLIENTE, "c")

    assert clave in entorno["almacen"].eliminados
    with pytest.raises(EvidenciaRechazada):
        await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id, CLIENTE, "c")


async def test_sin_cifrado_se_rechaza(entorno):
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno), "c")
    entorno["almacen"].simular_subida(resultado.evidencia.objeto_clave, JPEG, "image/jpeg", cifrado=None)

    with pytest.raises(EvidenciaRechazada):
        await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id, CLIENTE, "c")


async def test_una_evidencia_rechazada_no_afecta_a_las_demas(entorno):
    buena = await _subir_y_confirmar(entorno)
    mala = await entorno["solicitar"].ejecutar(_cmd(entorno), "c")
    entorno["almacen"].simular_subida(mala.evidencia.objeto_clave, b"basura" * 20, "image/jpeg")
    with pytest.raises(EvidenciaRechazada):
        await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, mala.evidencia.evidencia_id, CLIENTE, "c")

    detalle = await entorno["detalle"].ejecutar(entorno["siniestro"].siniestro_id, CLIENTE)

    estados = {e.evidencia_id: e.estado for e in detalle.evidencias}
    assert estados == {buena.evidencia_id: "CARGADA", mala.evidencia.evidencia_id: "RECHAZADA"}
    assert detalle.siniestro.estado == "REPORTADO"


async def test_confirmar_evidencia_de_otro_cliente(entorno):
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno), "c")

    with pytest.raises(EvidenciaNoEncontrada):
        await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id, OTRO_CLIENTE, "c")
    with pytest.raises(EvidenciaNoEncontrada):
        await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, uuid.uuid4(), CLIENTE, "c")


async def test_registrar_ubicacion_y_verla_en_el_detalle(entorno):
    ubicacion = UbicacionSiniestro(4.6533, -74.0836, 18.5, FuenteUbicacion.GPS, AHORA)

    await entorno["ubicacion"].ejecutar(entorno["siniestro"].siniestro_id, CLIENTE, ubicacion)
    detalle = await entorno["detalle"].ejecutar(entorno["siniestro"].siniestro_id, CLIENTE)

    assert detalle.siniestro.ubicacion.latitud == pytest.approx(4.6533)
    assert detalle.siniestro.ubicacion.fuente == FuenteUbicacion.GPS


async def test_ubicacion_de_siniestro_ajeno_o_futura(entorno):
    ubicacion = UbicacionSiniestro(4.6, -74.0, 10, FuenteUbicacion.RED, AHORA)

    with pytest.raises(SiniestroNoEncontrado):
        await entorno["ubicacion"].ejecutar(entorno["siniestro"].siniestro_id, OTRO_CLIENTE, ubicacion)
    with pytest.raises(FechaInvalida):
        await entorno["ubicacion"].ejecutar(
            entorno["siniestro"].siniestro_id, CLIENTE,
            UbicacionSiniestro(4.6, -74.0, 10, FuenteUbicacion.RED, AHORA + timedelta(hours=1)),
        )


async def test_el_detalle_oculta_las_pendientes_vencidas(entorno):
    await entorno["solicitar"].ejecutar(_cmd(entorno), "c")
    entorno["reloj"].ahora = AHORA + timedelta(minutes=11)

    detalle = await entorno["detalle"].ejecutar(entorno["siniestro"].siniestro_id, CLIENTE)

    assert detalle.evidencias == []


# --- Reintento con la misma Idempotency-Key (la app perdió la carga: se cerró, sin red o sesión vencida) ---

async def test_misma_clave_renueva_la_misma_evidencia_sin_gastar_cupo(entorno):
    clave = str(uuid.uuid4())
    video = dict(tipo=TipoEvidencia.VIDEO, tamano=len(MP4), clave_idempotencia=clave)
    primera = await entorno["solicitar"].ejecutar(_cmd(entorno, **video), "c")

    entorno["reloj"].ahora = AHORA + timedelta(minutes=2)
    segunda = await entorno["solicitar"].ejecutar(_cmd(entorno, **video), "c")

    assert not primera.reutilizada and segunda.reutilizada
    assert segunda.evidencia.evidencia_id == primera.evidencia.evidencia_id
    assert segunda.evidencia.objeto_clave == primera.evidencia.objeto_clave
    assert segunda.evidencia.expira_en == AHORA + timedelta(minutes=32)
    # Sigue habiendo un solo video: otro distinto sí choca con el máximo.
    with pytest.raises(LimiteEvidencias):
        await entorno["solicitar"].ejecutar(_cmd(entorno, tipo=TipoEvidencia.VIDEO, tamano=len(MP4)), "c")


async def test_misma_clave_vencida_se_renueva(entorno):
    clave = str(uuid.uuid4())
    await entorno["solicitar"].ejecutar(_cmd(entorno, clave_idempotencia=clave), "c")

    entorno["reloj"].ahora = AHORA + timedelta(hours=1)
    renovada = await entorno["solicitar"].ejecutar(_cmd(entorno, clave_idempotencia=clave), "c")

    assert renovada.reutilizada and renovada.evidencia.estado == "PENDIENTE"
    entorno["almacen"].simular_subida(renovada.evidencia.objeto_clave, JPEG, "image/jpeg")
    confirmada = await entorno["confirmar"].ejecutar(
        entorno["siniestro"].siniestro_id, renovada.evidencia.evidencia_id, CLIENTE, "c"
    )
    assert confirmada.estado == "CARGADA"


async def test_misma_clave_ya_cargada_no_entrega_otra_carga(entorno):
    clave = str(uuid.uuid4())
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno, clave_idempotencia=clave), "c")
    entorno["almacen"].simular_subida(resultado.evidencia.objeto_clave, JPEG, "image/jpeg")
    await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id, CLIENTE, "c")

    repetida = await entorno["solicitar"].ejecutar(_cmd(entorno, clave_idempotencia=clave), "c")

    assert repetida.reutilizada and repetida.carga is None and repetida.evidencia.estado == "CARGADA"


async def test_misma_clave_rechazada_u_otro_tipo(entorno):
    clave = str(uuid.uuid4())
    resultado = await entorno["solicitar"].ejecutar(_cmd(entorno, clave_idempotencia=clave), "c")
    entorno["almacen"].simular_subida(resultado.evidencia.objeto_clave, MP4, "image/jpeg")
    with pytest.raises(EvidenciaRechazada):
        await entorno["confirmar"].ejecutar(entorno["siniestro"].siniestro_id, resultado.evidencia.evidencia_id, CLIENTE, "c")

    with pytest.raises(EvidenciaRechazada):
        await entorno["solicitar"].ejecutar(_cmd(entorno, clave_idempotencia=clave), "c")
    with pytest.raises(IdempotenciaConflicto):
        await entorno["solicitar"].ejecutar(
            _cmd(entorno, tipo=TipoEvidencia.VIDEO, tamano=len(MP4), clave_idempotencia=clave), "c"
        )
