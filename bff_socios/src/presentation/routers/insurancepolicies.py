from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.infrastructure.gateways.insurancepolicies_service_gateway import InsurancePoliciesServiceGateway
from src.infrastructure.gateways.quotingengine_service_gateway import QuotingEngineServiceGateway
from src.presentation.dependencies import (
    cliente_autorizado,
    get_insurancepolicies_service_gateway,
    get_quotingengine_service_gateway,
    validar_cotizacion,
)
from src.presentation.http_utils import headers_backend, leer_multipart, response_backend, uuid_field

router = APIRouter(tags=["Pólizas"])


@router.post("/cotizaciones/{cotizacion_id}/firma-digital", status_code=201)
@router.get("/cotizaciones/{cotizacion_id}/firma-digital")
@router.get("/cotizaciones/{cotizacion_id}/poliza")
async def firma_y_poliza(
    cotizacion_id: UUID,
    request: Request,
    cliente_id: UUID = Depends(cliente_autorizado),
    gateway: InsurancePoliciesServiceGateway = Depends(get_insurancepolicies_service_gateway),
    quoting: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> Response:
    await validar_cotizacion(quoting, cotizacion_id, cliente_id)
    suffix = request.scope["route"].path.split("{cotizacion_id}", 1)[1]
    body = None
    if request.method == "POST":
        body, form = await leer_multipart(request, 2 * 1024 * 1024)
        try:
            values = form.getlist("cliente_id")
            if len(values) != 1 or uuid_field(values[0], "cliente_id") != cliente_id:
                raise HTTPException(403, "El cliente no coincide con el autorizado.")
        finally:
            await form.close()
    return response_backend(
        await gateway.cotizacion(
            request.method, cotizacion_id, suffix, body, headers_backend(request, cliente_id)
        )
    )
