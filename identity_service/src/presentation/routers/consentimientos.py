from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.use_cases.consultar_auditoria_consentimiento_use_case import (
    AuditoriaClienteNoEncontradoError,
    AuditoriaCriterioInvalidoError,
    ConsultarAuditoriaConsentimientoUseCase,
)
from src.presentation.dependencies import (
    get_consultar_auditoria_consentimiento_use_case,
)
from src.presentation.schemas import AuditoriaConsentimientoResponse

router = APIRouter(prefix="/consentimientos", tags=["Consentimientos"])


@router.get(
    "",
    response_model=AuditoriaConsentimientoResponse,
    status_code=status.HTTP_200_OK,
)
async def consultar_auditoria(
    identificacion: str | None = Query(default=None, max_length=30),
    correo: str | None = Query(default=None, max_length=254),
    use_case: ConsultarAuditoriaConsentimientoUseCase = Depends(
        get_consultar_auditoria_consentimiento_use_case
    ),
) -> AuditoriaConsentimientoResponse:
    try:
        auditoria = await use_case.ejecutar(identificacion, correo)
    except AuditoriaCriterioInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AuditoriaClienteNoEncontradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay un cliente con ese dato.",
        ) from exc
    return AuditoriaConsentimientoResponse.model_validate(auditoria)
