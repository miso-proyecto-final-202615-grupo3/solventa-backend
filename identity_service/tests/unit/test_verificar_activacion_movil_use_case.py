from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from sqlalchemy.exc import IntegrityError

from src.application.ports.liveness import (
    LivenessAdapterUnavailableError,
    LivenessInvalidCaptureError,
    LivenessSessionCancelledError,
    LivenessSessionConflictError,
    LivenessVerification,
    LivenessVerificationPort,
)
from src.application.use_cases.verificar_activacion_movil_use_case import (
    CapturaActivacionInvalidaError,
    IntentosActivacionAgotadosError,
    SesionActivacionCanceladaError,
    SesionActivacionInvalidaError,
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
    def __init__(self, result=None, unavailable=False, error=None):
        self.result = result or LivenessVerification("folio-1", True)
        self.unavailable = unavailable
        self.error = error
        self.kwargs = None

    async def start_session(self, *args):
        raise AssertionError("No se usa al verificar")

    async def cancel_session(self, *args):
        raise AssertionError("No se usa al verificar")

    async def verify(self, *args, **kwargs):
        self.kwargs = kwargs
        if self.unavailable:
            raise LivenessAdapterUnavailableError()
        if self.error:
            raise self.error
        return self.result


def crear_use_case(consumidos=0, liveness=None, activaciones=None, rollbacks=None):
    clientes = ClientesFake()
    activaciones = activaciones or ActivacionesFake(clientes.cliente.id.value, consumidos)
    commits = []

    async def commit():
        commits.append(True)

    async def rollback():
        if rollbacks is not None:
            rollbacks.append(True)

    return (
        VerificarActivacionMovilUseCase(
            clientes, activaciones, liveness or LivenessFake(), commit, ahora=lambda: AHORA,
            rollback=rollback,
        ),
        activaciones,
        commits,
    )


async def test_aprueba_y_retorna_el_contrato_canonico():
    use_case, activaciones, _ = crear_use_case(consumidos=1)

    result = await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert result.resultado == "APROBADO"
    assert result.intento == 2
    # Un aprobado no consume cupo.
    assert result.intentos_restantes == 2
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


async def test_rechazo_consume_un_intento():
    use_case, activaciones, _ = crear_use_case(
        consumidos=1, liveness=LivenessFake(result=LivenessVerification("propio-2", False, "GESTO_NO_DETECTADO"))
    )

    result = await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert result.resultado == "RECHAZADO"
    assert result.intentos_restantes == 1
    assert result.motivo == "GESTO_NO_DETECTADO"
    assert not activaciones.vinculos


async def test_conflicto_del_adaptador_anula_el_intento():
    use_case, activaciones, _ = crear_use_case(liveness=LivenessFake(error=LivenessSessionConflictError()))

    with pytest.raises(SesionActivacionInvalidaError):
        await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert activaciones.estados_intento[-1][1] == EstadoIntento.ANULADO
    assert activaciones.estados_sesion[-1] == ("sesion-1", EstadoSesion.CANCELADA)


async def test_sdk_cancelado_no_consume_intento():
    use_case, activaciones, _ = crear_use_case(liveness=LivenessFake(error=LivenessSessionCancelledError()))

    with pytest.raises(SesionActivacionCanceladaError):
        await use_case.ejecutar("ana@example.com", "sesion-1", None, {}, {}, "corr-1", sdk_result="CANCELLED")

    assert activaciones.estados_intento[-1][1] == EstadoIntento.ANULADO


async def test_sdk_con_proveedor_caido_deja_la_sesion_reutilizable():
    clientes = ClientesFake()
    activaciones = ActivacionesFake(clientes.cliente.id.value)
    activaciones.sesion = activaciones.sesion.__class__(**{**activaciones.sesion.__dict__, "tipo_captura": "SDK"})
    use_case, activaciones, _ = crear_use_case(liveness=LivenessFake(unavailable=True), activaciones=activaciones)

    with pytest.raises(VerificacionPruebaVidaNoDisponibleError):
        await use_case.ejecutar("ana@example.com", "sesion-1", None, {}, {}, "corr-1", sdk_result="COMPLETED")

    assert activaciones.estados_sesion[-1] == ("sesion-1", EstadoSesion.CREADA)


async def test_conflicto_de_vinculo_hace_rollback_y_anula():
    clientes = ClientesFake()
    activaciones = ActivacionesFake(clientes.cliente.id.value)

    async def vinculo_duplicado(*args):
        raise IntegrityError("insert", {}, Exception("uq_dispositivo_activo_instalacion"))

    activaciones.vincular_dispositivo = vinculo_duplicado
    rollbacks = []
    use_case, activaciones, _ = crear_use_case(activaciones=activaciones, rollbacks=rollbacks)

    with pytest.raises(VerificacionPruebaVidaNoDisponibleError):
        await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert rollbacks == [True]
    assert activaciones.estados_intento[-1][1] == EstadoIntento.ANULADO


async def test_envia_el_resultado_del_sdk_al_adaptador():
    liveness = LivenessFake()
    use_case, _, _ = crear_use_case(liveness=liveness)

    await use_case.ejecutar("ana@example.com", "sesion-1", None, {}, {}, "corr-1", sdk_result="COMPLETED")

    assert liveness.kwargs == {"sdk_result": "COMPLETED"}


async def test_captura_invalida_anula_sin_consumir_intento():
    use_case, activaciones, _ = crear_use_case(liveness=LivenessFake(error=LivenessInvalidCaptureError()))

    with pytest.raises(CapturaActivacionInvalidaError):
        await use_case.ejecutar("ana@example.com", "sesion-1", "nonce", {}, {}, "corr-1")

    assert activaciones.estados_intento[-1][1] == EstadoIntento.ANULADO
    assert activaciones.estados_sesion[-1] == ("sesion-1", EstadoSesion.CANCELADA)
