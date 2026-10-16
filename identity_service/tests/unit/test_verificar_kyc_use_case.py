import uuid
from datetime import date

import pytest

from src.application.ports.kyc import KycVerifier
from src.application.use_cases.verificar_kyc_use_case import (
    KycClienteNoEncontradoError,
    VerificarKycUseCase,
)
from src.domain.clientes.entities import Cliente, ClienteId
from src.domain.consentimiento.entities import ConsentimientoInicial
from src.domain.clientes.repositories import ClienteRepository
from src.domain.clientes.value_objects import EstadoKYC


def _cliente() -> Cliente:
    return Cliente(
        id=ClienteId(),
        nombres="Ana",
        apellidos="Pérez",
        tipo_documento="CC",
        numero_identificacion="1020304050",
        correo="ana.perez@example.com",
        fecha_nacimiento=date(1990, 5, 15),
        pais_residencia="Colombia",
        telefono="+573001234567",
        estado_kyc=EstadoKYC.PENDIENTE,
    )


class InMemoryKycRepository(ClienteRepository):
    def __init__(self, clientes: list[Cliente] | None = None):
        self.clientes: list[Cliente] = clientes or []
        self.actualizados: list[tuple[ClienteId, EstadoKYC]] = []

    async def existe_por_correo(self, correo: str) -> bool:
        return any(c.correo == correo for c in self.clientes)

    async def existe_por_documento(
        self, tipo_documento: str, numero_identificacion: str
    ) -> bool:
        return any(
            c.tipo_documento == tipo_documento
            and c.numero_identificacion == numero_identificacion
            for c in self.clientes
        )

    async def guardar(
        self, cliente: Cliente, consentimiento: ConsentimientoInicial
    ) -> None:
        self.clientes.append(cliente)

    async def obtener_por_id(self, cliente_id: ClienteId) -> Cliente | None:
        return next(
            (c for c in self.clientes if c.id == cliente_id), None
        )

    async def actualizar_estado_kyc(
        self, cliente_id: ClienteId, estado_kyc: EstadoKYC
    ) -> None:
        self.actualizados.append((cliente_id, estado_kyc))
        cliente = await self.obtener_por_id(cliente_id)
        if cliente:
            cliente.estado_kyc = estado_kyc


class FakeKyc(KycVerifier):
    def __init__(self, resultado: EstadoKYC):
        self.resultado = resultado

    async def verificar(
        self, tipo_documento: str, numero_identificacion: str
    ) -> EstadoKYC:
        return self.resultado


async def test_verifica_y_actualiza_estado_kyc():
    cliente = _cliente()
    repo = InMemoryKycRepository([cliente])
    verifier = FakeKyc(EstadoKYC.VALIDADO)
    use_case = VerificarKycUseCase(repo, verifier)

    resultado = await use_case.ejecutar(cliente.id.value)

    assert resultado.estado_kyc == EstadoKYC.VALIDADO
    assert repo.actualizados == [(cliente.id, EstadoKYC.VALIDADO)]


async def test_lanza_error_si_el_cliente_no_existe():
    repo = InMemoryKycRepository()
    verifier = FakeKyc(EstadoKYC.VALIDADO)
    use_case = VerificarKycUseCase(repo, verifier)

    with pytest.raises(KycClienteNoEncontradoError):
        await use_case.ejecutar(uuid.uuid4())