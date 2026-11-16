from hmac import compare_digest
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from src.core.config import settings
from src.domain.verificaciones_kyc_aml.repositories import AuditoriaKycAmlRepository
from src.presentation.dependencies import get_auditoria_kyc_aml_repository
from src.presentation.schemas.verificacion_kyc_aml_schemas import (
    EventoTrazabilidadKycAmlResponse,
)

router = APIRouter(prefix="/cotizaciones", tags=["Auditoría de emisión"])


@router.get(
    "/{cotizacion_id}/trazabilidad-kyc-aml",
    response_model=list[EventoTrazabilidadKycAmlResponse],
    include_in_schema=False,
)
async def consultar_trazabilidad_kyc_aml(
    cotizacion_id: UUID,
    internal_token: str | None = Header(default=None, alias="X-Audit-Internal-Token"),
    auditoria: AuditoriaKycAmlRepository = Depends(get_auditoria_kyc_aml_repository),
) -> list[EventoTrazabilidadKycAmlResponse]:
    esperado = settings.TRAZABILIDAD_INTERNAL_TOKEN
    if not esperado or not internal_token or not compare_digest(esperado, internal_token):
        raise HTTPException(status_code=403, detail="Consulta interna no autorizada.")
    eventos = await auditoria.listar_por_cotizacion(cotizacion_id)
    return [EventoTrazabilidadKycAmlResponse.model_validate(evento) for evento in eventos]
