import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.infrastructure.gateways.backend_gateway import json_object
from src.infrastructure.gateways.payments_service_gateway import PaymentsServiceGateway
from src.infrastructure.gateways.quotingengine_service_gateway import QuotingEngineServiceGateway
from src.presentation.dependencies import (
    cliente_autorizado,
    get_payments_service_gateway,
    get_quotingengine_service_gateway,
    validar_cotizacion,
)
from src.presentation.http_utils import headers_backend, leer_cuerpo, response_backend, uuid_field

router = APIRouter(tags=["Pagos"])


@router.get("/cotizaciones/{cotizacion_id}/resumen-pago")
async def resumen_pago(
    cotizacion_id: UUID,
    request: Request,
    cliente_id: UUID = Depends(cliente_autorizado),
    gateway: PaymentsServiceGateway = Depends(get_payments_service_gateway),
    quoting: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> Response:
    await validar_cotizacion(quoting, cotizacion_id, cliente_id)
    return response_backend(await gateway.resumen_pago(cotizacion_id, headers_backend(request)))


@router.post("/pagos", status_code=201)
async def pago(
    request: Request,
    cliente_id: UUID = Depends(cliente_autorizado),
    gateway: PaymentsServiceGateway = Depends(get_payments_service_gateway),
    quoting: QuotingEngineServiceGateway = Depends(get_quotingengine_service_gateway),
) -> Response:
    body = await leer_cuerpo(request, 1024 * 1024)
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, "Solicitud JSON inválida.") from exc
    if not isinstance(payload, dict) or uuid_field(payload.get("cliente_id"), "cliente_id") != cliente_id:
        raise HTTPException(403, "El cliente no coincide con el autorizado.")
    await validar_cotizacion(quoting, uuid_field(payload.get("cotizacion_id"), "cotizacion_id"), cliente_id)
    return response_backend(await gateway.crear_pago(body, headers_backend(request)))


@router.get("/pagos/{pago_id}")
async def consultar_pago(
    pago_id: UUID,
    request: Request,
    cliente_id: UUID = Depends(cliente_autorizado),
    gateway: PaymentsServiceGateway = Depends(get_payments_service_gateway),
) -> Response:
    response = await gateway.obtener_pago(pago_id, headers_backend(request))
    data = json_object(response)
    try:
        propietario = UUID(data["cliente_id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(502, "Respuesta inválida del servicio de pagos.") from exc
    if propietario != cliente_id:
        raise HTTPException(403, "El pago no pertenece al cliente autorizado.")
    return response_backend(response)
