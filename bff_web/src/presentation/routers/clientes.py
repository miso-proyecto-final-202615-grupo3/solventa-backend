import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_identity_service_gateway
router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post(
    "/registro",
    status_code=status.HTTP_201_CREATED,
)
async def registrar_cliente(
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.registrar_cliente(
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.post(
    "/autenticar",
    status_code=status.HTTP_200_OK,
)
async def autenticar_cliente(
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.autenticar_cliente(
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.put(
    "/{cliente_id}/consentimiento",
    status_code=status.HTTP_200_OK,
)
async def actualizar_consentimiento(
    cliente_id: uuid.UUID,
    request: Request,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.actualizar_consentimiento(
            str(cliente_id),
            await request.body(),
            request.headers.get("content-type", "application/json"),
        )
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.get(
    "/{cliente_id}/perfil",
    status_code=status.HTTP_200_OK,
)
async def obtener_perfil_cliente(
    cliente_id: uuid.UUID,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.obtener_perfil_cliente(str(cliente_id))
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc