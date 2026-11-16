from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from emision_fakes import (
    AHORA,
    FIRMA_BYTES,
    AlmacenamientoCertificadosFalso,
    AlmacenamientoFirmasFalso,
    FirmasEnMemoria,
    GeneracionesEnMemoria,
    GeneradorFalso,
    PolizasEnMemoria,
    Transaccion,
    contrato_de,
    hace,
    poliza_emitida,
    vinculada,
)

from src.application.ports.generador_pdf import GeneracionPdfError
from src.application.use_cases.errores_poliza import PolizaNoEncontradaError
from src.application.use_cases.generar_certificado_use_case import (
    DatosCertificadoIncompletosError,
    FirmaAlteradaError,
    GenerarCertificadoPolizaUseCase,
    GeneracionEnCursoError,
)
from src.domain.certificados.entities import EstadoGeneracion, GeneracionCertificado
from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoError,
    GeneracionEnCursoDuplicadaError,
)
from src.domain.firmas.repositories import AlmacenamientoFirmaError
from src.domain.polizas.entities import EstadoCertificado

BOGOTA = ZoneInfo("America/Bogota")


class Escenario:
    def __init__(self, con_contrato=True, con_firma=True, **cambios_poliza) -> None:
        self.poliza = poliza_emitida(**cambios_poliza)
        self.polizas = PolizasEnMemoria()
        self.polizas.polizas[self.poliza.poliza_id] = self.poliza
        if con_contrato:
            self.polizas.contratos[self.poliza.poliza_id] = contrato_de(self.poliza)
        self.polizas.confirmar()
        self.firma = vinculada(self.poliza)
        self.firmas = FirmasEnMemoria(self.firma) if con_firma else FirmasEnMemoria()
        self.generaciones = GeneracionesEnMemoria()
        self.alm_firmas = AlmacenamientoFirmasFalso()
        self.alm_certificados = AlmacenamientoCertificadosFalso()
        self.generador = GeneradorFalso()
        self.tx = Transaccion(self.polizas, self.generaciones)
        self.ahora = AHORA
        self.caso = GenerarCertificadoPolizaUseCase(
            self.polizas,
            self.firmas,
            self.generaciones,
            self.alm_firmas,
            self.alm_certificados,
            self.generador,
            self.tx.commit,
            self.tx.rollback,
            BOGOTA,
            timedelta(minutes=5),
            lambda: self.ahora,
        )

    async def generar(self):
        return await self.caso.ejecutar(self.poliza.poliza_id, "corr-1")

    @property
    def ruta(self) -> str:
        return f"certificados-poliza/{self.poliza.cliente_id}/{self.poliza.poliza_id}/certificado-poliza.pdf"


async def test_genera_guarda_y_asocia_el_certificado_a_la_poliza():
    e = Escenario()

    resultado = await e.generar()

    assert resultado.generado is True
    assert e.alm_certificados.archivos == {e.ruta: b"%PDF-1.7 falso"}
    guardada = e.polizas.polizas[e.poliza.poliza_id]
    assert guardada.estado_certificado == EstadoCertificado.GENERADO
    assert guardada.ruta_certificado == e.ruta
    assert resultado.poliza.estado_certificado == EstadoCertificado.GENERADO
    assert e.tx.commits == 2 and e.tx.rollbacks == 0


async def test_la_ruta_del_certificado_es_por_cliente_y_poliza():
    e = Escenario()

    await e.generar()

    assert e.ruta == (
        f"certificados-poliza/{e.poliza.cliente_id}/{e.poliza.poliza_id}/certificado-poliza.pdf"
    )
    assert not e.ruta.startswith("/")


async def test_deja_auditoria_con_inicio_fin_ruta_plantilla_y_datos():
    e = Escenario()

    await e.generar()

    (generacion,) = e.generaciones.generaciones
    assert generacion.estado == EstadoGeneracion.GENERADO
    assert generacion.iniciada_en == AHORA and generacion.finalizada_en == AHORA
    assert generacion.ruta_certificado == e.ruta
    assert generacion.plantilla == "certificado_poliza.html"
    assert generacion.correlation_id == "corr-1"
    assert generacion.error_codigo is None
    assert generacion.datos_plantilla["poliza"]["numero"] == "POL-20261113-AB12CD34"
    assert generacion.datos_plantilla["titular"]["nombre"] == "María Fernanda Rodríguez Castañeda"


async def test_el_generador_recibe_los_datos_y_la_imagen_de_la_firma_por_separado():
    e = Escenario()

    await e.generar()

    (datos, imagen, tipo) = e.generador.llamadas[0]
    assert imagen == FIRMA_BYTES and tipo == "image/png"
    assert datos["firma"]["firma_id"] == str(e.firma.firma_id)
    assert datos["firma"]["fingerprint_contrato"] == "f" * 64
    # la imagen no se guarda en la auditoría
    assert "base64" not in str(datos) and FIRMA_BYTES.decode("latin-1") not in str(datos)


async def test_las_fechas_son_solo_fecha_en_la_zona_horaria_configurada():
    e = Escenario(
        vigencia_desde=datetime(2026, 11, 13, 3, 30, tzinfo=UTC),
        vigencia_hasta=datetime(2036, 11, 13, 4, 59, tzinfo=UTC),
        emitida_en=datetime(2026, 11, 13, 5, 0, tzinfo=UTC),
    )

    await e.generar()

    datos = e.generador.llamadas[0][0]
    # 03:30Z es el 12 en Bogotá (UTC-5); 05:00Z ya es el 13
    assert datos["poliza"]["vigencia_desde"] == "2026-11-12"
    assert datos["poliza"]["vigencia_hasta"] == "2036-11-12"
    assert datos["poliza"]["emitida_en"] == "2026-11-13"
    assert datos["firma"]["capturada_en"] == "2026-11-12"
    assert datos["generado_en"] == "2026-11-13"
    assert datos["condiciones"]["aceptadas_en"] == "2026-11-12"


async def test_si_ya_esta_generado_no_hace_nada():
    e = Escenario(estado_certificado=EstadoCertificado.GENERADO, ruta_certificado="ruta/previa.pdf")

    resultado = await e.generar()

    assert resultado.generado is False
    assert e.generador.llamadas == [] and e.generaciones.generaciones == []
    assert e.polizas.polizas[e.poliza.poliza_id].ruta_certificado == "ruta/previa.pdf"
    assert e.tx.commits == 0


async def test_poliza_inexistente():
    e = Escenario()
    del e.polizas.polizas[e.poliza.poliza_id]

    with pytest.raises(PolizaNoEncontradaError):
        await e.generar()


@pytest.mark.parametrize("faltante", ["contrato", "firma"])
async def test_exige_contrato_y_firma_vinculada(faltante):
    e = Escenario(con_contrato=faltante != "contrato", con_firma=faltante != "firma")

    with pytest.raises(DatosCertificadoIncompletosError):
        await e.generar()

    assert e.generaciones.generaciones == [] and e.generador.llamadas == []


@pytest.mark.parametrize(
    ("preparar", "error", "codigo"),
    [
        (lambda e: setattr(e.alm_firmas, "contenido", b"otra imagen"), FirmaAlteradaError, "FIRMA_ALTERADA"),
        (lambda e: setattr(e.generador, "error", GeneracionPdfError("2 páginas")), GeneracionPdfError, "PDF_INVALIDO"),
        (
            lambda e: setattr(e.alm_certificados, "error", AlmacenamientoCertificadoError("S3 caído")),
            AlmacenamientoCertificadoError,
            "ALMACENAMIENTO_NO_DISPONIBLE",
        ),
        (
            lambda e: setattr(e.alm_firmas, "error", AlmacenamientoFirmaError("sin firma")),
            AlmacenamientoFirmaError,
            "ALMACENAMIENTO_NO_DISPONIBLE",
        ),
        (lambda e: setattr(e.generador, "error", RuntimeError("boom")), RuntimeError, "ERROR_INESPERADO"),
    ],
)
async def test_un_fallo_deja_la_generacion_fallida_y_la_poliza_pendiente(preparar, error, codigo):
    e = Escenario()
    preparar(e)
    e.ahora = AHORA

    with pytest.raises(error):
        await e.generar()

    (generacion,) = e.generaciones.generaciones
    assert generacion.estado == EstadoGeneracion.FALLIDO
    assert generacion.error_codigo == codigo
    assert generacion.finalizada_en == AHORA and generacion.ruta_certificado is None
    assert generacion.error_detalle and len(generacion.error_detalle) <= 500
    guardada = e.polizas.polizas[e.poliza.poliza_id]
    assert guardada.estado_certificado == EstadoCertificado.PENDIENTE and guardada.ruta_certificado is None
    assert e.tx.rollbacks == 1


async def test_el_reintento_tras_un_fallo_genera_otra_fila_y_termina_bien():
    e = Escenario()
    e.generador.error = GeneracionPdfError("fallo transitorio")
    with pytest.raises(GeneracionPdfError):
        await e.generar()
    e.generador.error = None

    resultado = await e.generar()

    assert resultado.generado is True
    assert [g.estado for g in e.generaciones.generaciones] == [
        EstadoGeneracion.FALLIDO,
        EstadoGeneracion.GENERADO,
    ]


async def test_otra_generacion_reciente_en_proceso_no_se_pisa():
    e = Escenario()
    e.generaciones.generaciones.append(
        GeneracionCertificado(
            poliza_id=e.poliza.poliza_id,
            cliente_id=e.poliza.cliente_id,
            plantilla="certificado_poliza.html",
            datos_plantilla={},
            iniciada_en=hace(1),
            correlation_id="otra",
        )
    )
    e.generaciones.confirmar()

    with pytest.raises(GeneracionEnCursoError):
        await e.generar()

    assert e.generador.llamadas == []
    assert len(e.generaciones.generaciones) == 1
    assert e.generaciones.generaciones[0].estado == EstadoGeneracion.EN_PROCESO


async def test_una_generacion_abandonada_se_cierra_y_se_reintenta():
    e = Escenario()
    e.generaciones.generaciones.append(
        GeneracionCertificado(
            poliza_id=e.poliza.poliza_id,
            cliente_id=e.poliza.cliente_id,
            plantilla="certificado_poliza.html",
            datos_plantilla={},
            iniciada_en=hace(10),
            correlation_id="caida",
        )
    )
    e.generaciones.confirmar()

    resultado = await e.generar()

    assert resultado.generado is True
    abandonada, nueva = e.generaciones.generaciones
    assert abandonada.estado == EstadoGeneracion.FALLIDO and abandonada.error_codigo == "ABANDONADA"
    assert nueva.estado == EstadoGeneracion.GENERADO


async def test_una_carrera_al_crear_la_generacion_se_informa_como_en_curso():
    e = Escenario()

    async def duplicada(generacion):
        raise GeneracionEnCursoDuplicadaError()

    e.generaciones.crear = duplicada

    with pytest.raises(GeneracionEnCursoError):
        await e.generar()

    assert e.tx.rollbacks == 1 and e.generador.llamadas == []


async def test_si_otro_proceso_cerro_la_generacion_no_registra_fallo_ni_pisa_la_poliza():
    e = Escenario()

    async def ya_cerrada(generacion):
        return False

    e.generaciones.actualizar = ya_cerrada

    with pytest.raises(GeneracionEnCursoError):
        await e.generar()

    assert e.polizas.polizas[e.poliza.poliza_id].estado_certificado == EstadoCertificado.PENDIENTE
    assert e.generaciones.generaciones[0].estado == EstadoGeneracion.EN_PROCESO


async def test_si_falla_el_commit_final_queda_fallida_y_se_puede_reintentar():
    e = Escenario()
    llamadas = []
    commit_real = e.tx.commit

    async def commit():
        llamadas.append(1)
        if len(llamadas) == 2:
            raise RuntimeError("commit falló")
        await commit_real()

    e.caso._commit = commit

    with pytest.raises(RuntimeError):
        await e.generar()

    assert e.generaciones.generaciones[0].estado == EstadoGeneracion.FALLIDO
    assert e.generaciones.generaciones[0].error_codigo == "ERROR_INESPERADO"
