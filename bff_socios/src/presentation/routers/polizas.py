from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from src.infrastructure.gateways.insurancepolicies_service_gateway import InsurancePoliciesServiceGateway
from src.presentation.dependencies import cliente_autorizado, get_insurancepolicies_service_gateway
from src.presentation.http_utils import headers_backend, response_backend

router = APIRouter(tags=["Pólizas"])


@router.get("/polizas/{poliza_id}")
@router.get("/polizas/{poliza_id}/certificado")
@router.get("/polizas/{poliza_id}/certificado/descarga")
@router.get("/polizas/mis-polizas")
async def polizas(
    request: Request,
    poliza_id: UUID | None = None,
    cliente_id: UUID = Depends(cliente_autorizado),
    gateway: InsurancePoliciesServiceGateway = Depends(get_insurancepolicies_service_gateway),
) -> Response:
    suffix = request.url.path.split("/polizas", 1)[1]
    return response_backend(await gateway.polizas(suffix, headers_backend(request, cliente_id)))
