from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.application.ports.liveness import (
    LivenessAdapterUnavailableError,
    LivenessVerification,
    LivenessVerificationPort,
)
from src.application.use_cases.verificar_activacion_movil_use_case import (
    IntentosActivacionAgotadosError,
    VerificacionPruebaVidaNoDisponibleError,
    VerificarActivacionMovilUseCase,
)
from src.domain.activacion_movil.entities import (
    DatosDispositivo,
    EstadoIntento,
    EstadoSesion,
    Plataforma,
    SesionActivacion,
)
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.value_objects import EstadoKYC


AHORA = datetime(2026, 10, 31, 12, tzinfo=UTC)


class ClientesFake:
    def __init__(self):
        self.cliente = Cliente(
            id=ClienteId(), nombres="Ana", apellidos="Pérez", tipo_documento="CC",
            numero_identificacion="1020304050", correo="ana@example.com",
            fecha_nacimiento=AHORA.date(), pais_residencia="Colombia", telefono="3001234567",
            estado_kyc=EstadoKYC.VALIDADO,
        )

    async def obtener_por_correo(self, correo):
        return self.cliente if correo == self.cliente.correo else None

    async def bloquear_para_actualizar(self, cliente_id):
        return self.cliente


class ActivacionesFake:
    def __init__(self, cliente_id, consumidos=0):
        self.consumidos = consumidos
        self.recuperaciones = []
        self.intentos = []
        self.estados_sesion = []
        self.estados_intento = []
        self.vinculos = []
        self.sesion = SesionActivacion(
            id="sesion-1", cliente_id=cliente_id,
            dispositivo=DatosDispositivo(uuid4(), Plataforma.ANDROID, "Pixel", "15"),
            tipo_captura="FRAMES", estado=EstadoSesion.CREADA,
            creada_en=AHORA - timedelta(minutes=1), expira_en=AHORA + timedelta(minutes=1),
        )

    async def anular_intentos_en_curso_vencidos(self, *args):
        self.recuperaciones.append(args)
        return 0

    async def contar_intentos_consumidos(self, *args):
        return self.consumidos

    async def obtener_sesion(self, cliente_id, sesion_id):
        return self.sesion if sesion_id == self.sesion.id else None

    async def guardar_intento(self, intento):
        self.intentos.append(intento)

    async def actualizar_estado_sesion(self, sesion_id, estado):
        self.estados_sesion.append((sesion_id, estado))

    async def actualizar_estado_intento(self, intento_id, estado, *args, **kwargs):
        self.estados_intento.append((intento_id, estado, kwargs))

    async def vincular_dispositivo(self, *args):
        self.vinculos.append(args)


class LivenessFake(LivenessVerificationPort):
    def __init__(self, result=None, unavailable=False):
        self.result = result or LivenessVerification("folio-1", True)
        self.unavailable = unavailable

    async def start_session(self, *args):
        raise AssertionError("No se usa al verificar")

    async def cancel_session(self, *args):
        raise AssertionError("No se usa al verificar")

    async def verify(self, *args):
        if self.unavailable:
            raise LivenessAdapterUnavailableError()
        return self.result


def crear_use_case(consumidos=0, liveness=None):
    clientes = ClientesFake()
    activaciones = ActivacionesFake(clientes.cliente.id.value, consumidos)
    commits = []

    async def commit():
        commits.append(True)

    return (
        VerificarActivacionMovilUseCase(
            clientes, activaciones, liveness or LivenessFake(), commit, ahora=lambda: AHORA
        ),
        activaciones,
        commits,
    )


async def test_aprueba_y_retorna_el_contrato_canonico():
    use_case, activaciones, _ = crear_use_case(consumidos=1)

    result = await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert result.resultado == "APROBADO"
    assert result.intento == 2
    assert result.intentos_restantes == 1
    assert result.dispositivo_vinculado is True
    assert activaciones.vinculos


async def test_rechaza_el_cuarto_intento_antes_de_llamar_al_adaptador():
    use_case, activaciones, _ = crear_use_case(consumidos=3)

    with pytest.raises(IntentosActivacionAgotadosError):
        await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert not activaciones.intentos
    assert activaciones.recuperaciones


async def test_anula_el_intento_si_el_adaptador_no_esta_disponible():
    use_case, activaciones, commits = crear_use_case(liveness=LivenessFake(unavailable=True))

    with pytest.raises(VerificacionPruebaVidaNoDisponibleError):
        await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert activaciones.estados_intento[-1][1] == EstadoIntento.ANULADO
    assert activaciones.estados_sesion[-1] == ("sesion-1", EstadoSesion.CANCELADA)
    assert len(commits) == 2
