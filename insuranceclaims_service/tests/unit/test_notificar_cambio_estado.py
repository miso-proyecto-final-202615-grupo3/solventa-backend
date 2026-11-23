"""HU4.2.2 · Envío al dueño del siniestro (CA3), tokens inválidos (N8) y errores transitorios."""
import logging
import uuid

import pytest

from src.application.ports.destinos_push import DestinoPush, DestinosPush
from src.application.ports.notificador_push import NotificadorPush, ResultadoEnvio
from src.application.use_cases.notificar_cambio_estado_use_case import ErrorTransitorioPush, NotificarCambioEstadoUseCase
from src.domain.siniestros.entities import EventoOutbox, Siniestro
from tests.fakes import AHORA, CLIENTE, OTRO_CLIENTE

TOKEN_A = "token-dispositivo-a-" + "x" * 40 + "AAAAAA"
TOKEN_B = "token-dispositivo-b-" + "y" * 40 + "BBBBBB"
TOKEN_AJENO = "token-de-otro-cliente-" + "z" * 40 + "ZZZZZZ"


class DestinosFalsos(DestinosPush):
    def __init__(self, por_cliente: dict) -> None:
        self.por_cliente = por_cliente
        self.consultas: list = []
        self.eliminados: list[str] = []

    async def listar(self, cliente_id, correlation_id):
        self.consultas.append((cliente_id, correlation_id))
        return self.por_cliente.get(cliente_id, [])

    async def eliminar(self, token, correlation_id):
        self.eliminados.append(token)


class NotificadorFalso(NotificadorPush):
    def __init__(self, resultados: dict | None = None) -> None:
        self.resultados = resultados or {}
        self.envios: list[tuple[str, dict]] = []

    async def enviar(self, token, plataforma, datos):
        self.envios.append((token, datos))
        return self.resultados.get(token, ResultadoEnvio.ENVIADO)


def _siniestro(cliente=CLIENTE) -> Siniestro:
    return Siniestro(
        poliza_id=uuid.uuid4(), tipo="ROBO", estado="EN_EVALUACION", clave_idempotencia="k",
        ocurrido_en=AHORA, reportado_en=AHORA, cliente_id=cliente, numero="SIN-2026-ABCDEF01",
    )


def _evento(siniestro: Siniestro) -> EventoOutbox:
    return EventoOutbox(
        tipo="SINIESTRO_ESTADO", agregado_id=siniestro.siniestro_id,
        payload={"tipo": "SINIESTRO_ESTADO", "siniestro_id": str(siniestro.siniestro_id),
                 "numero": siniestro.numero, "estado": siniestro.estado},
    )


def _destinos() -> DestinosFalsos:
    return DestinosFalsos({
        CLIENTE: [DestinoPush("i-a", TOKEN_A, "ANDROID"), DestinoPush("i-b", TOKEN_B, "ANDROID")],
        OTRO_CLIENTE: [DestinoPush("i-z", TOKEN_AJENO, "ANDROID")],
    })


async def test_envia_solo_a_los_dispositivos_del_dueno_con_el_payload_del_contrato(caplog):
    caplog.set_level(logging.INFO)
    siniestro = _siniestro()
    evento = _evento(siniestro)
    destinos, notificador = _destinos(), NotificadorFalso()

    enviados = await NotificarCambioEstadoUseCase(destinos, notificador).ejecutar(evento, siniestro)

    assert enviados == 2
    assert [token for token, _ in notificador.envios] == [TOKEN_A, TOKEN_B]
    assert destinos.consultas == [(CLIENTE, str(evento.evento_id))]
    assert notificador.envios[0][1] == {
        "tipo": "SINIESTRO_ESTADO", "siniestro_id": str(siniestro.siniestro_id),
        "numero": "SIN-2026-ABCDEF01", "estado": "EN_EVALUACION", "evento_id": str(evento.evento_id),
    }
    assert TOKEN_A not in caplog.text and TOKEN_AJENO not in caplog.text


async def test_sin_destinos_no_es_error():
    siniestro = _siniestro(cliente=uuid.uuid4())

    enviados = await NotificarCambioEstadoUseCase(_destinos(), NotificadorFalso()).ejecutar(_evento(siniestro), siniestro)

    assert enviados == 0


async def test_token_invalido_se_elimina_y_sigue_con_los_demas():
    siniestro = _siniestro()
    destinos = _destinos()
    notificador = NotificadorFalso({TOKEN_A: ResultadoEnvio.TOKEN_INVALIDO})

    enviados = await NotificarCambioEstadoUseCase(destinos, notificador).ejecutar(_evento(siniestro), siniestro)

    assert enviados == 1
    assert destinos.eliminados == [TOKEN_A]


async def test_error_transitorio_hace_reintentar_el_evento_sin_borrar_el_token():
    siniestro = _siniestro()
    destinos = _destinos()
    notificador = NotificadorFalso({TOKEN_B: ResultadoEnvio.ERROR_TRANSITORIO})

    with pytest.raises(ErrorTransitorioPush):
        await NotificarCambioEstadoUseCase(destinos, notificador).ejecutar(_evento(siniestro), siniestro)

    assert destinos.eliminados == []
    assert len(notificador.envios) == 2  # el otro dispositivo sí recibió


async def test_siniestro_sin_dueno_no_consulta_destinos():
    siniestro = _siniestro(cliente=None)
    destinos = _destinos()

    assert await NotificarCambioEstadoUseCase(destinos, NotificadorFalso()).ejecutar(_evento(siniestro), siniestro) == 0
    assert destinos.consultas == []
