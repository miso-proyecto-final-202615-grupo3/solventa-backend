from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.infrastructure.gateways.payments_service_gateway import (
    PaymentsGatewayError,
    PaymentsServiceGateway,
)
from src.presentation.dependencies import get_payments_service_gateway

router = APIRouter(tags=["Pagos"])
_HEADERS_PERMITIDOS = ("authorization", "idempotency-key", "x-correlation-id")


def _headers(request: Request) -> dict[str, str]:
    return {
        key: value for key, value in request.headers.items() if key in _HEADERS_PERMITIDOS
    }


@router.get("/cotizaciones/{cotizacion_id}/resumen-pago")
async def obtener_resumen_pago(
    cotizacion_id: UUID,
    request: Request,
    response: Response,
    gateway: PaymentsServiceGateway = Depends(get_payments_service_gateway),
) -> dict[str, Any]:
    try:
        status_code, body = await gateway.obtener_resumen_pago(cotizacion_id, _headers(request))
    except PaymentsGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    response.status_code = status_code
    return body


@router.post(
    "/pagos",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reintento idempotente"}},
    openapi_extra={
        "parameters": [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string"},
            },
            {
                "name": "X-Correlation-Id",
                "in": "header",
                "required": False,
                "schema": {"type": "string"},
            },
        ],
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["cotizacion_id", "cliente_id"],
                        "properties": {
                            "cotizacion_id": {"type": "string", "format": "uuid"},
                            "cliente_id": {"type": "string", "format": "uuid"},
                            "metodo_pago": {
                                "type": "string",
                                "enum": ["PAYPAL", "TARJETA_CREDITO"],
                                "default": "PAYPAL",
                            },
                            "paypal_email": {"type": "string"},
                            "numero_tarjeta": {"type": "string", "pattern": "^[0-9]{13,19}$"},
                            "mes_expiracion": {"type": "integer", "minimum": 1, "maximum": 12},
                            "anio_expiracion": {"type": "integer", "minimum": 2000, "maximum": 2100},
                            "cvv": {"type": "string", "pattern": "^[0-9]{3,4}$"},
                        },
                        "description": (
                            "PAYPAL requiere paypal_email; TARJETA_CREDITO requiere "
                            "numero_tarjeta, mes_expiracion, anio_expiracion y cvv."
                        ),
                    }
                }
            },
        },
    },
)
async def procesar_pago(
    request: Request,
    response: Response,
    gateway: PaymentsServiceGateway = Depends(get_payments_service_gateway),
) -> dict[str, Any]:
    headers = _headers(request)
    if "content-type" in request.headers:
        headers["content-type"] = request.headers["content-type"]
    try:
        status_code, body = await gateway.procesar_pago(await request.body(), headers)
    except PaymentsGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    response.status_code = status_code
    return body


@router.get("/pagos/{pago_id}")
async def obtener_pago(
    pago_id: UUID,
    request: Request,
    response: Response,
    gateway: PaymentsServiceGateway = Depends(get_payments_service_gateway),
) -> dict[str, Any]:
    try:
        status_code, body = await gateway.obtener_pago(pago_id, _headers(request))
    except PaymentsGatewayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    response.status_code = status_code
    return body
