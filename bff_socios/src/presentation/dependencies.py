from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException

from src.infrastructure.gateways.backend_gateway import json_object
from src.infrastructure.gateways.identity_service_gateway import IdentityServiceGateway
from src.infrastructure.gateways.insurancepolicies_service_gateway import InsurancePoliciesServiceGateway
from src.infrastructure.gateways.payments_service_gateway import PaymentsServiceGateway
from src.infrastructure.gateways.quotingengine_service_gateway import QuotingEngineServiceGateway


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


def get_identity_service_gateway(
    client: httpx.AsyncClient = Depends(get_http_client),
) -> IdentityServiceGateway:
    return IdentityServiceGateway(client)


def get_quotingengine_service_gateway(
    client: httpx.AsyncClient = Depends(get_http_client),
) -> QuotingEngineServiceGateway:
    return QuotingEngineServiceGateway(client)


def get_insurancepolicies_service_gateway(
    client: httpx.AsyncClient = Depends(get_http_client),
) -> InsurancePoliciesServiceGateway:
    return InsurancePoliciesServiceGateway(client)


def get_payments_service_gateway(
    client: httpx.AsyncClient = Depends(get_http_client),
) -> PaymentsServiceGateway:
    return PaymentsServiceGateway(client)


async def socio_autenticado(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> UUID:
    if not x_api_key:
        raise HTTPException(401, "Se requiere X-API-Key.")
    data = json_object(await gateway.validar_api_key(x_api_key))
    try:
        return UUID(data["socio_id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(502, "Respuesta inválida del servicio de identidad.") from exc


async def cliente_autorizado(
    x_client_id: UUID = Header(alias="X-Client-Id"),
    socio_id: UUID = Depends(socio_autenticado),
    gateway: IdentityServiceGateway = Depends(get_identity_service_gateway),
) -> UUID:
    response = await gateway.validar_asociacion(socio_id, x_client_id)
    if response.status_code != 204:
        json_object(response)
        raise HTTPException(502, "Respuesta inválida del servicio de identidad.")
    return x_client_id


async def validar_cotizacion(
    gateway: QuotingEngineServiceGateway, cotizacion_id: UUID, cliente_id: UUID,
) -> None:
    data = json_object(await gateway.obtener_cotizacion(cotizacion_id))
    try:
        propietario = UUID(data["cliente_id"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(502, "Respuesta inválida del servicio de cotización.") from exc
    if propietario != cliente_id:
        raise HTTPException(403, "La cotización no pertenece al cliente autorizado.")
