"""API interna de evidencias y ubicación del siniestro (HU4.1.2). La consume el BFF Móvil.

Nunca registra la URL firmada, los campos de la política ni las coordenadas.
"""
import uuid

from fastapi import APIRouter, Depends, Header, Response, status

from src.application.use_cases.evidencias_use_cases import (
    ConfirmarCargaEvidenciaUseCase,
    RegistrarUbicacionUseCase,
    SolicitarCargaEvidenciaUseCase,
    SolicitudCargaCmd,
)
from src.domain.siniestros.ubicacion import UbicacionSiniestro
from src.presentation.dependencies import (
    get_confirmar_carga_use_case,
    get_registrar_ubicacion_use_case,
    get_solicitar_carga_use_case,
)
from src.presentation.schemas.evidencias import (
    CargaResponse,
    EvidenciaResponse,
    RegistrarUbicacionResponse,
    SolicitudCargaRequest,
    SolicitudCargaResponse,
    UbicacionRequest,
    UbicacionResponse,
)

router = APIRouter(prefix="/siniestros", tags=["Evidencias del siniestro"])


def _correlation(correlation_id: str | None) -> str:
    return correlation_id or str(uuid.uuid4())


@router.post(
    "/{siniestro_id}/evidencias",
    response_model=SolicitudCargaResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reintento con la misma Idempotency-Key: la misma evidencia, con carga nueva o ya CARGADA."}},
)
async def solicitar_carga(
    siniestro_id: uuid.UUID,
    payload: SolicitudCargaRequest,
    response: Response,
    cliente_id: uuid.UUID = Header(alias="X-Cliente-Id"),
    idempotency_key: uuid.UUID | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: SolicitarCargaEvidenciaUseCase = Depends(get_solicitar_carga_use_case),
) -> SolicitudCargaResponse:
    """Registra la evidencia en `PENDIENTE` y entrega la carga prefirmada para subir directo al almacenamiento.

    Con `Idempotency-Key` (una por evidencia local de la app), repetir la solicitud no crea otra evidencia:
    renueva la carga de la misma (`200`) o informa que ya quedó `CARGADA` (`200`, `carga: null`).
    """
    resultado = await use_case.ejecutar(
        SolicitudCargaCmd(
            siniestro_id=siniestro_id,
            cliente_id=cliente_id,
            tipo=payload.tipo,
            content_type=payload.content_type,
            tamano_bytes=payload.tamano_bytes,
            origen=payload.origen,
            capturada_en=payload.capturada_en,
            clave_idempotencia=str(idempotency_key) if idempotency_key else None,
        ),
        _correlation(correlation_id),
    )
    if resultado.reutilizada:
        response.status_code = status.HTTP_200_OK
    carga = resultado.carga
    return SolicitudCargaResponse(
        evidencia_id=resultado.evidencia.evidencia_id,
        estado=resultado.evidencia.estado,
        carga=None if carga is None else CargaResponse(
            url=carga.url,
            campos=carga.campos,
            expira_en=carga.expira_en,
            tamano_max_bytes=resultado.tamano_max_bytes,
        ),
    )


@router.post("/{siniestro_id}/evidencias/{evidencia_id}/confirmacion", response_model=EvidenciaResponse)
async def confirmar_carga(
    siniestro_id: uuid.UUID,
    evidencia_id: uuid.UUID,
    cliente_id: uuid.UUID = Header(alias="X-Cliente-Id"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: ConfirmarCargaEvidenciaUseCase = Depends(get_confirmar_carga_use_case),
) -> EvidenciaResponse:
    """Verifica el archivo subido (tamaño, tipo, cifrado y firma de bytes). Idempotente."""
    evidencia = await use_case.ejecutar(siniestro_id, evidencia_id, cliente_id, _correlation(correlation_id))
    return EvidenciaResponse.desde(evidencia)


@router.put("/{siniestro_id}/ubicacion", response_model=RegistrarUbicacionResponse)
async def registrar_ubicacion(
    siniestro_id: uuid.UUID,
    payload: UbicacionRequest,
    cliente_id: uuid.UUID = Header(alias="X-Cliente-Id"),
    use_case: RegistrarUbicacionUseCase = Depends(get_registrar_ubicacion_use_case),
) -> RegistrarUbicacionResponse:
    """Registra o reemplaza la ubicación del evento."""
    siniestro = await use_case.ejecutar(
        siniestro_id,
        cliente_id,
        UbicacionSiniestro(
            latitud=payload.latitud,
            longitud=payload.longitud,
            precision_m=payload.precision_m,
            fuente=payload.fuente,
            capturada_en=payload.capturada_en,
        ),
    )
    return RegistrarUbicacionResponse(
        ubicacion=UbicacionResponse.desde(siniestro),
        actualizada_en=siniestro.ubicacion_actualizada_en,
    )
