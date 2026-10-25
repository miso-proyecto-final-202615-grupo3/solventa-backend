from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineGatewayError,
    QuotingEngineServiceGateway,
)
from src.presentation.dependencies import get_quotingengine_service_gateway

router = APIRouter(tags=["Cotización"])


@router.get("/productos", status_code=status.HTTP_200_OK)
async def listar_productos(
    gateway: QuotingEngineServiceGateway = Depends(
        get_quotingengine_service_gateway
    ),
) -> list[dict[str, Any]]:
    return await _ejecutar(gateway.listar_productos)


@router.get("/productos/{codigo}", status_code=status.HTTP_200_OK)
async def obtener_producto(
    codigo: str,
    gateway: QuotingEngineServiceGateway = Depends(
        get_quotingengine_service_gateway
    ),
) -> dict[str, Any]:
    return await _ejecutar(lambda: gateway.obtener_producto(codigo))


@router.post("/cotizaciones", status_code=status.HTTP_201_CREATED)
async def solicitar_cotizacion(
    request: Request,
    gateway: QuotingEngineServiceGateway = Depends(
        get_quotingengine_service_gateway
    ),
) -> dict[str, Any]:
    try:
        return await gateway.solicitar_cotizacion(
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except QuotingEngineGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.get(
    "/cotizaciones/{cotizacion_id}",
    status_code=status.HTTP_200_OK,
)
async def obtener_cotizacion(
    cotizacion_id: UUID,
    gateway: QuotingEngineServiceGateway = Depends(
        get_quotingengine_service_gateway
    ),
) -> dict[str, Any]:
    return await _ejecutar(
        lambda: gateway.obtener_cotizacion(str(cotizacion_id))
    )


async def _ejecutar(
    operation: Callable[[], Awaitable[Any]],
) -> Any:
    try:
        return await operation()
    except QuotingEngineGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc
