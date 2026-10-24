import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.application.use_cases.obtener_perfil_financiero_use_case import (
    ClientePerfilNoEncontradoError,
    ConsentimientoNoActivoError,
    ObtenerPerfilFinancieroUseCase,
)
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.clientes.value_objects import EstadoKYC
from src.domain.consentimiento.entities import (
    ConsentimientoActual,
    EstadoConsentimiento,
)
from src.domain.perfilamiento.entities import PerfilOpenFinance


CLIENTE_ID = uuid.uuid4()


class FakeClienteRepository:
    def __init__(self, cliente: Cliente | None):
        self.cliente = cliente

    async def obtener_por_id(self, cliente_id: ClienteId):
        if self.cliente is not None and self.cliente.id == cliente_id:
            return self.cliente
        return None


class FakeConsentimientoRepository:
    def __init__(self, estado: EstadoConsentimiento | None):
        self.estado = estado

    async def obtener_actual(self, cliente_id: uuid.UUID):
        if self.estado is None:
            return None
        return ConsentimientoActual(
            cliente_id=cliente_id,
            estado=self.estado,
            otorgado_en=None,
            revocado_en=None,
        )


class FakeOpenFinanceGateway:
    def __init__(self):
        self.llamadas = 0
        self.resultado = PerfilOpenFinance(
            ingreso_mensual=Decimal("8500000"),
            ahorros_liquidos=Decimal("25500000"),
            dti_pct=Decimal("28"),
            sobregiros_12_meses=0,
            score=820,
        )

    async def obtener_perfil_financiero(self, cliente_id: uuid.UUID):
        self.llamadas += 1
        return self.resultado


def crear_cliente() -> Cliente:
    return Cliente(
        id=ClienteId(CLIENTE_ID),
        nombres="Ana",
        apellidos="Pérez",
        tipo_documento="CC",
        numero_identificacion="1020304050",
        correo="ana@example.com",
        fecha_nacimiento=date(1990, 5, 15),
        pais_residencia="Colombia",
        telefono="+573001234567",
        estado_kyc=EstadoKYC.PENDIENTE,
    )


def crear_use_case(estado: EstadoConsentimiento | None):
    gateway = FakeOpenFinanceGateway()
    use_case = ObtenerPerfilFinancieroUseCase(
        FakeClienteRepository(crear_cliente()),
        FakeConsentimientoRepository(estado),
        gateway,
    )
    return use_case, gateway


async def test_consulta_open_finance_con_consentimiento_activo():
    use_case, gateway = crear_use_case(EstadoConsentimiento.ACEPTADO)

    perfil = await use_case.ejecutar(CLIENTE_ID)

    assert gateway.llamadas == 1
    assert perfil.dti_pct == Decimal("28")
    assert perfil.ahorros_liquidos == Decimal("25500000")


@pytest.mark.parametrize(
    "estado", [None, EstadoConsentimiento.REVOCADO]
)
async def test_no_consulta_open_finance_sin_consentimiento_activo(estado):
    use_case, gateway = crear_use_case(estado)

    with pytest.raises(ConsentimientoNoActivoError):
        await use_case.ejecutar(CLIENTE_ID)

    assert gateway.llamadas == 0


async def test_cliente_inexistente_no_consulta_open_finance():
    gateway = FakeOpenFinanceGateway()
    use_case = ObtenerPerfilFinancieroUseCase(
        FakeClienteRepository(None),
        FakeConsentimientoRepository(EstadoConsentimiento.ACEPTADO),
        gateway,
    )

    with pytest.raises(ClientePerfilNoEncontradoError):
        await use_case.ejecutar(CLIENTE_ID)

    assert gateway.llamadas == 0
