import uuid
from datetime import UTC, datetime

import pytest

from src.application.use_cases.consultar_auditoria_consentimiento_use_case import (
    AuditoriaClienteNoEncontradoError,
    AuditoriaCriterioInvalidoError,
    ConsultarAuditoriaConsentimientoUseCase,
)
from src.domain.consentimiento.auditoria import (
    AuditoriaConsentimiento,
    AuditoriaConsentimientoRepository,
    ClienteAuditado,
    EventoAuditoriaConsentimiento,
)
from src.domain.consentimiento.entities import EstadoConsentimiento


def _auditoria() -> AuditoriaConsentimiento:
    cliente_id = uuid.uuid4()
    return AuditoriaConsentimiento(
        cliente=ClienteAuditado(
            id=cliente_id,
            nombres="Ana",
            apellidos="Pérez",
            tipo_documento="CC",
            numero_identificacion="1020304050",
            correo="ana@example.com",
            estado_consentimiento=EstadoConsentimiento.ACEPTADO,
        ),
        eventos=[
            EventoAuditoriaConsentimiento(
                id=uuid.uuid4(),
                tipo_accion="ACEPTACION",
                fecha=datetime.now(UTC),
                version_terminos="1.0",
                canal="web",
            )
        ],
    )


class FakeAuditoriaRepository(AuditoriaConsentimientoRepository):
    def __init__(self, auditoria: AuditoriaConsentimiento | None) -> None:
        self.auditoria = auditoria
        self.consultas: list[tuple[str, str]] = []

    async def buscar_por_correo(self, correo: str):
        self.consultas.append(("correo", correo))
        return self.auditoria

    async def buscar_por_identificacion(self, numero_identificacion: str):
        self.consultas.append(("identificacion", numero_identificacion))
        return self.auditoria


async def test_busca_por_correo():
    repo = FakeAuditoriaRepository(_auditoria())

    resultado = await ConsultarAuditoriaConsentimientoUseCase(repo).ejecutar(
        correo=" ana@example.com "
    )

    assert resultado is repo.auditoria
    assert repo.consultas == [("correo", "ana@example.com")]


async def test_busca_por_identificacion():
    repo = FakeAuditoriaRepository(_auditoria())

    await ConsultarAuditoriaConsentimientoUseCase(repo).ejecutar(
        identificacion="1020304050"
    )

    assert repo.consultas == [("identificacion", "1020304050")]


@pytest.mark.parametrize(
    "criterios",
    [
        {},
        {"correo": "", "identificacion": ""},
        {"correo": "a@example.com", "identificacion": "12345"},
    ],
)
async def test_exige_exactamente_un_criterio(criterios):
    repo = FakeAuditoriaRepository(_auditoria())

    with pytest.raises(AuditoriaCriterioInvalidoError):
        await ConsultarAuditoriaConsentimientoUseCase(repo).ejecutar(**criterios)

    assert repo.consultas == []


async def test_cliente_inexistente_lanza_error():
    repo = FakeAuditoriaRepository(None)

    with pytest.raises(AuditoriaClienteNoEncontradoError):
        await ConsultarAuditoriaConsentimientoUseCase(repo).ejecutar(
            correo="nadie@example.com"
        )
