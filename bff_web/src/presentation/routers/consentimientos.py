from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_identity_service_gateway

router = APIRouter(prefix="/consentimientos", tags=["Consentimientos"])

_CRITERIOS = ("identificacion", "correo")


@router.get("", status_code=status.HTTP_200_OK)
async def consultar_auditoria_consentimiento(
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    params = {
        criterio: request.query_params[criterio]
        for criterio in _CRITERIOS
        if criterio in request.query_params
    }
    try:
        return await gateway.consultar_auditoria_consentimiento(params)
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc
