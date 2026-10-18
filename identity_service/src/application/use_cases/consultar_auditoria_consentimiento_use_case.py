from src.domain.consentimiento.auditoria import (
    AuditoriaConsentimiento,
    AuditoriaConsentimientoRepository,
)


class AuditoriaCriterioInvalidoError(Exception):
    """Debe indicarse exactamente uno: número de identificación o correo."""


class AuditoriaClienteNoEncontradoError(Exception):
    pass


class ConsultarAuditoriaConsentimientoUseCase:
    def __init__(self, repository: AuditoriaConsentimientoRepository) -> None:
        self.repository = repository

    async def ejecutar(
        self,
        identificacion: str | None = None,
        correo: str | None = None,
    ) -> AuditoriaConsentimiento:
        identificacion = (identificacion or "").strip() or None
        correo = (correo or "").strip() or None
        if (identificacion is None) == (correo is None):
            raise AuditoriaCriterioInvalidoError(
                "Indica el número de identidad o el correo, solo uno de los dos."
            )

        if identificacion is not None:
            auditoria = await self.repository.buscar_por_identificacion(
                identificacion
            )
        else:
            auditoria = await self.repository.buscar_por_correo(correo)

        if auditoria is None:
            raise AuditoriaClienteNoEncontradoError
        return auditoria
