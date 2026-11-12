from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesGatewayError,
    InsurancePoliciesServiceGateway,
)
from src.presentation.dependencies import get_insurancepolicies_service_gateway

router = APIRouter(prefix="/polizas", tags=["Pólizas"])


@router.get("/mis-polizas", status_code=status.HTTP_200_OK)
async def listar_mis_polizas(
    client_id: UUID = Header(alias="X-Client-Id"),
    gateway: InsurancePoliciesServiceGateway = Depends(
        get_insurancepolicies_service_gateway
    ),
) -> list[dict]:
    try:
        return await gateway.listar_mis_polizas(str(client_id))
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


@router.get("/{poliza_id}", status_code=status.HTTP_200_OK)
async def obtener_poliza(
    poliza_id: UUID,
    client_id: UUID = Header(alias="X-Client-Id"),
    gateway: InsurancePoliciesServiceGateway = Depends(
        get_insurancepolicies_service_gateway
    ),
) -> dict:
    try:
        return await gateway.obtener_poliza(str(poliza_id), str(client_id))
    except InsurancePoliciesGatewayError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
