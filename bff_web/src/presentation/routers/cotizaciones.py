from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.infrastructure.gateways.cotizacion_service_gateway import (
    CotizacionGatewayError,
    CotizacionServiceGateway,
)
from src.presentation.dependencies import get_cotizacion_service_gateway

router = APIRouter(prefix="/cotizaciones", tags=["Cotizaciones"])


@router.post("", status_code=status.HTTP_200_OK)
async def cotizar(
    request: Request,
    gateway: CotizacionServiceGateway = Depends(
        get_cotizacion_service_gateway
    ),
) -> dict:
    try:
        return await gateway.cotizar(
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except CotizacionGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
