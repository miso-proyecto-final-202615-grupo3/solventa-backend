from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.application.ports.consentimiento_biometrico import ConsentimientoBiometricoPort
from src.application.ports.liveness import LivenessSessionInfo, LivenessVerificationPort
from src.application.use_cases.iniciar_activacion_movil_use_case import (
    ClienteNoRegistradoError,
    ConsentimientoBiometricoRequeridoError,
    IniciarActivacionMovilUseCase,
    IntentosAgotadosError,
)
from src.domain.activacion_movil.entities import (
    DatosDispositivo,
    EstadoSesion,
    Plataforma,
    SesionActivacion,
)
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.value_objects import EstadoKYC


AHORA = datetime(2026, 10, 25, 12, tzinfo=UTC)


def _cliente() -> Cliente:
    return Cliente(
        id=ClienteId(), nombres="Ana", apellidos="Pérez", tipo_documento="CC",
        numero_identificacion="1020304050", correo="ana@example.com",
        fecha_nacimiento=AHORA.date(), pais_residencia="Colombia", telefono="3001234567",
        estado_kyc=EstadoKYC.VALIDADO,
    )


def _dispositivo() -> DatosDispositivo:
    return DatosDispositivo(uuid4(), Plataforma.ANDROID, "Pixel", "15")


class ClientesFake:
    def __init__(self, cliente: Cliente | None):
        self.cliente = cliente
        self.bloqueos = 0

    async def obtener_por_correo(self, correo):
        return self.cliente if self.cliente and self.cliente.correo == correo else None

    async def bloquear_para_actualizar(self, cliente_id):
        self.bloqueos += 1
        return self.cliente


class ActivacionesFake:
    def __init__(self, vinculado=False, consumidos=0, anterior=None):
        self.vinculado = vinculado
        self.consumidos = consumidos
        self.anterior = anterior
        self.canceladas = []
        self.sesiones = []

    async def dispositivo_esta_vinculado(self, cliente_id, installation_id):
        return self.vinculado

    async def contar_intentos_consumidos(self, cliente_id, desde):
        return self.consumidos

    async def obtener_sesion_creada(self, installation_id):
        return self.anterior

    async def cancelar_sesion(self, sesion_id):
        self.canceladas.append(sesion_id)

    async def guardar_sesion(self, sesion):
        self.sesiones.append(sesion)


class ConsentimientoFake(ConsentimientoBiometricoPort):
    def __init__(self, otorgado=True):
        self._otorgado = otorgado

    async def otorgado(self, cliente_id):
        return self._otorgado


class LivenessFake(LivenessVerificationPort):
    def __init__(self):
        self.canceladas = []

    async def start_session(self, customer_id, correlation_id):
        return LivenessSessionInfo(
            "sesion-nueva", "2026-10-25T12:02:00Z", {"type": "FRAMES", "nonce": "reto"}
        )

    async def cancel_session(self, session_id, correlation_id):
        self.canceladas.append(session_id)


def _use_case(cliente=None, activaciones=None, consentimiento=None, liveness=None):
    commits = []

    async def commit():
        commits.append(True)

    use_case = IniciarActivacionMovilUseCase(
        ClientesFake(cliente or _cliente()), activaciones or ActivacionesFake(),
        consentimiento or ConsentimientoFake(), liveness or LivenessFake(), commit,
        ahora=lambda: AHORA,
    )
    return use_case, commits


async def test_crea_sesion_nueva_y_reporta_intentos_restantes():
    activaciones = ActivacionesFake(consumidos=1)
    use_case, commits = _use_case(activaciones=activaciones)

    result = await use_case.ejecutar("ana@example.com", _dispositivo(), "corr-1")

    assert result.sesion_id == "sesion-nueva"
    assert result.intentos_restantes == 2
    assert result.captura == {"type": "FRAMES", "nonce": "reto"}
    assert len(activaciones.sesiones) == 1
    assert commits == [True]


async def test_no_crea_reto_si_el_dispositivo_ya_esta_vinculado():
    use_case, commits = _use_case(activaciones=ActivacionesFake(vinculado=True))

    result = await use_case.ejecutar("ana@example.com", _dispositivo(), "corr-1")

    assert result.dispositivo_vinculado is True
    assert result.sesion_id is None
    assert commits == []


async def test_invalida_reto_previo_antes_de_crear_otro():
    dispositivo = _dispositivo()
    anterior = SesionActivacion(
        "sesion-anterior", uuid4(), dispositivo, "FRAMES", EstadoSesion.CREADA,
        AHORA - timedelta(minutes=1), AHORA + timedelta(minutes=1),
    )
    activaciones = ActivacionesFake(anterior=anterior)
    liveness = LivenessFake()
    use_case, commits = _use_case(activaciones=activaciones, liveness=liveness)

    await use_case.ejecutar("ana@example.com", dispositivo, "corr-1")

    assert activaciones.canceladas == ["sesion-anterior"]
    assert liveness.canceladas == ["sesion-anterior"]
    assert commits == [True, True]


async def test_rechaza_si_no_hay_consentimiento():
    use_case, _ = _use_case(consentimiento=ConsentimientoFake(otorgado=False))

    with pytest.raises(ConsentimientoBiometricoRequeridoError):
        await use_case.ejecutar("ana@example.com", _dispositivo(), "corr-1")


async def test_rechaza_si_los_intentos_estan_agotados():
    use_case, _ = _use_case(activaciones=ActivacionesFake(consumidos=3))

    with pytest.raises(IntentosAgotadosError):
        await use_case.ejecutar("ana@example.com", _dispositivo(), "corr-1")


async def test_rechaza_cliente_no_registrado():
    use_case, _ = _use_case(cliente=None)
    use_case._clientes = ClientesFake(None)

    with pytest.raises(ClienteNoRegistradoError):
        await use_case.ejecutar("ana@example.com", _dispositivo(), "corr-1")
