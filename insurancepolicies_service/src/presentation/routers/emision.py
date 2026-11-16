import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from src.application.use_cases.consultar_emision_use_cases import (
    CertificadoNoGeneradoError,
    ConsultarEstadoCertificadoUseCase,
    ConsultarPolizaPorCotizacionUseCase,
    DescargarCertificadoUseCase,
)
from src.application.use_cases.errores_poliza import (
    AccesoPolizaDenegadoError,
    PolizaNoEncontradaError,
)
from src.domain.certificados.repositories import (
    AlmacenamientoCertificadoError,
    CertificadoNoEncontradoError,
)
from src.domain.polizas.entities import EstadoCertificado
from src.presentation.dependencies import (
    get_consultar_estado_certificado_use_case,
    get_consultar_poliza_por_cotizacion_use_case,
    get_descargar_certificado_use_case,
)
from src.presentation.schemas.emision_schemas import (
    EstadoCertificadoResponse,
    GeneracionCertificadoResponse,
    ResumenPolizaResponse,
)

router = APIRouter(tags=["Emisión de pólizas"])

_NOMBRE_SEGURO = re.compile(r"[^A-Za-z0-9._-]")


def _error(status_code: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"codigo": codigo, "mensaje": mensaje})


def _no_encontrada() -> HTTPException:
    return _error(status.HTTP_404_NOT_FOUND, "POLIZA_NO_ENCONTRADA", "La póliza no existe o aún no fue emitida.")


def _acceso_denegado() -> HTTPException:
    return _error(status.HTTP_403_FORBIDDEN, "ACCESO_DENEGADO", "No puedes consultar esta póliza.")


@router.get("/cotizaciones/{cotizacion_id}/poliza", response_model=ResumenPolizaResponse)
async def obtener_poliza_por_cotizacion(
    cotizacion_id: uuid.UUID,
    client_id: uuid.UUID = Header(alias="X-Client-Id"),
    use_case: ConsultarPolizaPorCotizacionUseCase = Depends(
        get_consultar_poliza_por_cotizacion_use_case
    ),
) -> ResumenPolizaResponse:
    try:
        resumen = await use_case.ejecutar(cotizacion_id, client_id)
    except PolizaNoEncontradaError as exc:
        raise _no_encontrada() from exc
    except AccesoPolizaDenegadoError as exc:
        raise _acceso_denegado() from exc
    poliza = resumen.poliza
    return ResumenPolizaResponse(
        poliza_id=poliza.poliza_id,
        numero=poliza.numero,
        estado=poliza.estado,
        cotizacion_id=poliza.cotizacion_id,
        titular_nombre=poliza.titular_nombre,
        vigencia_desde=poliza.vigencia_desde,
        vigencia_hasta=poliza.vigencia_hasta,
        prima=resumen.prima,
        moneda=resumen.moneda,
        estado_certificado=poliza.estado_certificado,
    )


@router.get("/polizas/{poliza_id}/certificado", response_model=EstadoCertificadoResponse)
async def obtener_estado_certificado(
    poliza_id: uuid.UUID,
    client_id: uuid.UUID = Header(alias="X-Client-Id"),
    use_case: ConsultarEstadoCertificadoUseCase = Depends(get_consultar_estado_certificado_use_case),
) -> EstadoCertificadoResponse:
    try:
        estado = await use_case.ejecutar(poliza_id, client_id)
    except PolizaNoEncontradaError as exc:
        raise _no_encontrada() from exc
    except AccesoPolizaDenegadoError as exc:
        raise _acceso_denegado() from exc
    generacion = estado.ultima_generacion
    return EstadoCertificadoResponse(
        poliza_id=estado.poliza.poliza_id,
        estado_certificado=estado.poliza.estado_certificado,
        disponible=estado.poliza.estado_certificado == EstadoCertificado.GENERADO,
        ultima_generacion=GeneracionCertificadoResponse.model_validate(generacion)
        if generacion
        else None,
    )


@router.get(
    "/polizas/{poliza_id}/certificado/descarga",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Certificado en PDF"}},
)
async def descargar_certificado(
    poliza_id: uuid.UUID,
    client_id: uuid.UUID = Header(alias="X-Client-Id"),
    use_case: DescargarCertificadoUseCase = Depends(get_descargar_certificado_use_case),
) -> Response:
    try:
        certificado = await use_case.ejecutar(poliza_id, client_id)
    except PolizaNoEncontradaError as exc:
        raise _no_encontrada() from exc
    except AccesoPolizaDenegadoError as exc:
        raise _acceso_denegado() from exc
    except CertificadoNoGeneradoError as exc:
        raise _error(status.HTTP_409_CONFLICT, "CERTIFICADO_NO_GENERADO", str(exc)) from exc
    except CertificadoNoEncontradoError as exc:
        raise _error(
            status.HTTP_404_NOT_FOUND, "CERTIFICADO_NO_ENCONTRADO", "No se encontró el archivo del certificado."
        ) from exc
    except AlmacenamientoCertificadoError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ALMACENAMIENTO_NO_DISPONIBLE",
            "No se pudo leer el certificado.",
        ) from exc
    nombre = _NOMBRE_SEGURO.sub("_", certificado.nombre_archivo)
    return Response(
        content=certificado.contenido,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
