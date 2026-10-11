from fastapi import APIRouter, Depends, HTTPException, status

from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.presentation.dependencies import get_identity_service_gateway
from src.presentation.schemas import ClienteCreate, PasswordVerify

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post(
    "/registro",
    status_code=status.HTTP_201_CREATED,
)
async def registrar_cliente(
    payload: ClienteCreate,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.registrar_cliente(payload.model_dump(mode="json"))
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.post(
    "/autenticar",
    status_code=status.HTTP_200_OK,
)
async def autenticar_cliente(
    payload: PasswordVerify,
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> dict:
    try:
        return await gateway.autenticar_cliente(payload.model_dump(mode="json"))
    except IdentityGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc