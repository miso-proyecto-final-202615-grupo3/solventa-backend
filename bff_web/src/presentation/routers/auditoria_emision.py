import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.config import settings
from src.infrastructure.gateways.identity_service_gateway import (
    IdentityGatewayError,
    IdentityServiceGateway,
)
from src.infrastructure.gateways.insurancepolicies_service_gateway import (
    InsurancePoliciesGatewayError,
    InsurancePoliciesServiceGateway,
)
from src.infrastructure.gateways.payments_service_gateway import (
    PaymentsGatewayError,
    PaymentsServiceGateway,
)
from src.infrastructure.gateways.quotingengine_service_gateway import (
    QuotingEngineGatewayError,
    QuotingEngineServiceGateway,
)
from src.presentation.dependencies import (
    get_identity_service_gateway,
    get_insurancepolicies_service_gateway,
    get_payments_service_gateway,
    get_quotingengine_service_gateway,
    require_auditor,
)
from src.presentation.schemas.trazabilidad_emision import (
    EventoTrazabilidadResponse,
    TrazabilidadEmisionResponse,
)

router = APIRouter(prefix="/auditoria-emision", tags=["Auditoría de emisión"])


@router.get("", response_model=TrazabilidadEmisionResponse)
async def consultar_trazabilidad_emision(
    numero_poliza: str = Query(min_length=8, max_length=50),
    _auditor: str = Depends(require_auditor),
    polizas: InsurancePoliciesServiceGateway = Depends(
        get_insurancepolicies_service_gateway
    ),
    cotizaciones: QuotingEngineServiceGateway = Depends(
        get_quotingengine_service_gateway
    ),
    identidad: IdentityServiceGateway = Depends(get_identity_service_gateway),
    pagos: PaymentsServiceGateway = Depends(get_payments_service_gateway),
) -> TrazabilidadEmisionResponse:
    token = settings.TRAZABILIDAD_INTERNAL_TOKEN
    if not token:
        raise HTTPException(503, "La consulta de auditoría no está configurada.")

    try:
        referencia = await polizas.consultar_trazabilidad_poliza(numero_poliza, token)
    except InsurancePoliciesGatewayError as exc:
        if exc.status_code == 404:
            raise HTTPException(404, "No encontramos esa póliza.") from exc
        raise HTTPException(503, "No pudimos consultar el historial completo.") from exc

    try:
        cotizacion_id = UUID(str(referencia["cotizacion_id"]))
        cliente_id = UUID(str(referencia["cliente_id"]))
        poliza_id = UUID(str(referencia["poliza_id"]))
        if referencia["numero"] != numero_poliza or not isinstance(referencia["eventos"], list):
            raise ValueError("La referencia de póliza no es válida.")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, "El servicio de pólizas devolvió una referencia inválida.") from exc

    try:
        decisiones, verificaciones, eventos_pago = await asyncio.gather(
            cotizaciones.consultar_trazabilidad_condiciones(
                str(cotizacion_id), token
            ),
            identidad.consultar_trazabilidad_kyc_aml(
                str(cotizacion_id), token
            ),
            pagos.consultar_trazabilidad_pagos(cotizacion_id, token),
        )
    except (QuotingEngineGatewayError, IdentityGatewayError, PaymentsGatewayError) as exc:
        raise HTTPException(503, "No pudimos consultar el historial completo.") from exc

    try:
        eventos = [
            EventoTrazabilidadResponse.model_validate(evento)
            for evento in [*decisiones, *verificaciones, *eventos_pago, *referencia["eventos"]]
        ]
        if any(
            evento.cotizacion_id != cotizacion_id or evento.cliente_id != cliente_id
            for evento in eventos
        ):
            raise ValueError("El evento no pertenece a la póliza consultada.")
        eventos.sort(key=lambda evento: (evento.ocurrido_en, str(evento.evento_id)))
        resultado = TrazabilidadEmisionResponse(
            poliza_id=poliza_id,
            numero=referencia["numero"],
            cotizacion_id=cotizacion_id,
            cliente_id=cliente_id,
            eventos=eventos,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, "Una fuente devolvió eventos de auditoría inválidos.") from exc
    return resultado
