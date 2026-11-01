import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.application.use_cases.consentimiento_biometrico_use_case import (
    ClienteConsentimientoNoEncontradoError,
    FechaDecisionInvalidaError,
    GestionarConsentimientoBiometricoUseCase,
    VersionTerminosDesactualizadaError,
)
from src.domain.consentimiento_biometrico.entities import (
    DecisionBiometrica,
    DecisionConsentimientoBiometrico,
    EstadoConsentimientoBiometrico,
)
from src.infrastructure.gateways.consentimiento_biometrico_registrado import (
    ConsentimientoBiometricoRegistrado,
)

AHORA = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
CLIENTE_ID = uuid.uuid4()
INSTALACION = uuid.uuid4()


class _Id:
    value = CLIENTE_ID


class _Cliente:
    id = _Id()


class FakeClientes:
    async def obtener_por_correo(self, correo):
        return _Cliente() if correo == "ana@example.com" else None


class FakeConsentimientos:
    def __init__(self):
        self.registros: list[DecisionConsentimientoBiometrico] = []

    async def registrar(self, decision):
        self.registros.append(decision)

    async def ultima_decision(self, cliente_id):
        propios = [r for r in self.registros if r.cliente_id == cliente_id]
        return propios[-1] if propios else None


class Commit:
    def __init__(self):
        self.veces = 0

    async def __call__(self):
        self.veces += 1


@pytest.fixture
def repo():
    return FakeConsentimientos()


@pytest.fixture
def commit():
    return Commit()


@pytest.fixture
def use_case(repo, commit):
    return GestionarConsentimientoBiometricoUseCase(FakeClientes(), repo, "1.0", commit, ahora=lambda: AHORA)


async def _registrar(use_case, decision=DecisionBiometrica.ACEPTADO, version="1.0", decidido_en=AHORA):
    return await use_case.registrar("ana@example.com", decision, version, INSTALACION, decidido_en, "corr-1")


async def test_sin_decisiones_no_hay_consentimiento(use_case):
    estado = await use_case.consultar("ana@example.com")

    assert estado == EstadoConsentimientoBiometrico(False, "1.0", None, None)


async def test_aceptar_registra_y_otorga(use_case, repo, commit):
    registro = await _registrar(use_case)

    assert registro.registrado_en == AHORA
    assert repo.registros[0].installation_id == INSTALACION
    assert repo.registros[0].canal == "APP_MOVIL"
    assert commit.veces == 1
    estado = await use_case.consultar("ana@example.com")
    assert estado.otorgado is True
    assert estado.version_aceptada == "1.0"
    assert estado.decidido_en == AHORA


async def test_el_rechazo_tambien_queda_registrado_y_revoca(use_case, repo):
    await _registrar(use_case)
    await _registrar(use_case, DecisionBiometrica.RECHAZADO)

    assert [r.decision for r in repo.registros] == [DecisionBiometrica.ACEPTADO, DecisionBiometrica.RECHAZADO]
    estado = await use_case.consultar("ana@example.com")
    assert estado.otorgado is False
    assert estado.version_aceptada is None


async def test_version_de_terminos_distinta_a_la_vigente(use_case, repo):
    with pytest.raises(VersionTerminosDesactualizadaError):
        await _registrar(use_case, version="0.9")
    assert repo.registros == []


@pytest.mark.parametrize(
    "decidido_en",
    [
        AHORA + timedelta(minutes=6),
        AHORA - timedelta(hours=25),
        datetime(2026, 11, 2, 15, 0),
    ],
    ids=["futuro", "muy-antiguo", "sin-zona-horaria"],
)
async def test_fecha_de_decision_invalida(use_case, repo, decidido_en):
    with pytest.raises(FechaDecisionInvalidaError):
        await _registrar(use_case, decidido_en=decidido_en)
    assert repo.registros == []


async def test_tolera_desfase_del_reloj_del_dispositivo(use_case):
    registro = await _registrar(use_case, decidido_en=AHORA + timedelta(minutes=4))

    assert registro.decidido_en == AHORA + timedelta(minutes=4)


async def test_cliente_inexistente(use_case):
    with pytest.raises(ClienteConsentimientoNoEncontradoError):
        await use_case.consultar("nadie@example.com")
    with pytest.raises(ClienteConsentimientoNoEncontradoError):
        await use_case.registrar(
            "nadie@example.com", DecisionBiometrica.ACEPTADO, "1.0", INSTALACION, AHORA, "corr"
        )


def _decision(decision, version="1.0"):
    return DecisionConsentimientoBiometrico(CLIENTE_ID, decision, version, INSTALACION, AHORA, AHORA)


async def test_activacion_exige_aceptacion_de_la_version_vigente(repo):
    gateway = ConsentimientoBiometricoRegistrado(repo, "2.0", require_consent=True)

    assert await gateway.otorgado(CLIENTE_ID) is False
    repo.registros.append(_decision(DecisionBiometrica.ACEPTADO, "1.0"))
    assert await gateway.otorgado(CLIENTE_ID) is False
    repo.registros.append(_decision(DecisionBiometrica.ACEPTADO, "2.0"))
    assert await gateway.otorgado(CLIENTE_ID) is True
    repo.registros.append(_decision(DecisionBiometrica.RECHAZADO, "2.0"))
    assert await gateway.otorgado(CLIENTE_ID) is False


async def test_sin_requisito_no_consulta_el_consentimiento(repo):
    gateway = ConsentimientoBiometricoRegistrado(repo, "1.0", require_consent=False)

    assert await gateway.otorgado(CLIENTE_ID) is True
