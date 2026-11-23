import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.infrastructure.gateways.quotingengine_service_gateway import QuotingEngineServiceGateway
from src.presentation.dependencies import (
    cliente_autorizado,
    get_quotingengine_service_gateway,
    socio_autenticado,
    validar_cotizacion,
)
from src.presentation.http_utils import headers_backend, leer_cuerpo, response_backend, uuid_field

router = APIRouter(tags=["Cotización"])


@router.get("/productos")
@router.get("/productos/{codigo}")
async def productos(
    request: Request,
    codigo: str = "",
    socio_id: UUID = Depends(socio_autenticado),
    gateway: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> Response:
    return response_backend(await gateway.productos(codigo, headers_backend(request)))


@router.post("/cotizaciones", status_code=201)
async def crear_cotizacion(
    request: Request,
    cliente_id: UUID = Depends(cliente_autorizado),
    socio_id: UUID = Depends(socio_autenticado),
    gateway: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> Response:
    try:
        payload = json.loads(await leer_cuerpo(request, 1024 * 1024))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "Solicitud JSON inválida.") from exc
    if not isinstance(payload, dict) or uuid_field(payload.get("cliente_id"), "cliente_id") != cliente_id:
        raise HTTPException(403, "El cliente no coincide con el autorizado.")
    if payload.get("socio_id") is not None and uuid_field(payload["socio_id"], "socio_id") != socio_id:
        raise HTTPException(403, "El socio no coincide con la API key.")
    payload["socio_id"] = str(socio_id)
    headers = headers_backend(request)
    headers["content-type"] = "application/json"
    return response_backend(await gateway.crear_cotizacion(payload, headers))


@router.get("/cotizaciones/{cotizacion_id}")
@router.get("/cotizaciones/{cotizacion_id}/condiciones")
@router.post("/cotizaciones/{cotizacion_id}/condiciones/decisiones")
async def cotizaciones(
    cotizacion_id: UUID,
    request: Request,
    cliente_id: UUID = Depends(cliente_autorizado),
    gateway: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> Response:
    await validar_cotizacion(gateway, cotizacion_id, cliente_id)
    suffix = request.scope["route"].path.split("{cotizacion_id}", 1)[1]
    body = await leer_cuerpo(request, 1024 * 1024) if request.method == "POST" else None
    return response_backend(
        await gateway.cotizacion(request.method, cotizacion_id, suffix, body, headers_backend(request))
    )
