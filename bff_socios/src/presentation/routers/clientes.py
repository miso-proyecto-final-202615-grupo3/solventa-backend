from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.infrastructure.gateways.identity_service_gateway import IdentityServiceGateway
from src.infrastructure.gateways.quotingengine_service_gateway import QuotingEngineServiceGateway
from src.presentation.dependencies import (
    cliente_autorizado,
    get_identity_service_gateway,
    get_quotingengine_service_gateway,
    socio_autenticado,
    validar_cotizacion,
)
from src.presentation.http_utils import headers_backend, leer_cuerpo, leer_multipart, response_backend, uuid_field

router = APIRouter(tags=["Clientes"])


@router.post("/clientes/prospectos", status_code=201)
async def registrar_prospecto(
    request: Request,
    socio_id: UUID = Depends(socio_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> Response:
    body = await leer_cuerpo(request, 64 * 1024)
    return response_backend(await gateway.registrar_prospecto(socio_id, body, headers_backend(request)))


@router.put("/clientes/{cliente_id}/consentimiento")
@router.get("/clientes/{cliente_id}/perfil")
@router.post("/clientes/{cliente_id}/verificaciones-kyc-aml")
@router.get("/clientes/{cliente_id}/verificaciones-kyc-aml/{verificacion_id}")
async def clientes(
    cliente_id: UUID,
    request: Request,
    verificacion_id: UUID | None = None,
    autorizado: UUID = Depends(cliente_autorizado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
    quoting: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> Response:
    if cliente_id != autorizado:
        raise HTTPException(403, "El cliente no coincide con el autorizado.")
    suffix = request.scope["route"].path.split("{cliente_id}", 1)[1]
    if verificacion_id is not None:
        suffix = suffix.replace("{verificacion_id}", str(verificacion_id))
    if request.method == "POST" and suffix == "/verificaciones-kyc-aml":
        body, form = await leer_multipart(request, 12 * 1024 * 1024)
        try:
            values = form.getlist("cotizacion_id")
            if len(values) > 1:
                raise HTTPException(422, "cotizacion_id duplicado.")
            if values and values[0]:
                await validar_cotizacion(quoting, uuid_field(values[0], "cotizacion_id"), cliente_id)
        finally:
            await form.close()
    else:
        body = await leer_cuerpo(request, 1024 * 1024) if request.method == "PUT" else None
    return response_backend(
        await gateway.cliente(request.method, cliente_id, suffix, body, headers_backend(request))
    )
