import re
import uuid
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)

from src.application.use_cases.capturar_firma_digital_use_case import (
    CapturarFirmaDigitalUseCase,
    FirmaConcurrenteError,
    FirmaYaVinculadaError,
    IdempotencyKeyReutilizadaError,
)
from src.application.use_cases.consultar_firma_digital_use_case import (
    ConsultarFirmaDigitalUseCase,
    FirmaNoEncontradaError,
)
from src.core.config import settings
from src.domain.firmas.entities import ArchivoFirma, FirmaInvalidaError
from src.domain.firmas.repositories import AlmacenamientoFirmaError
from src.presentation.dependencies import (
    get_capturar_firma_digital_use_case,
    get_consultar_firma_digital_use_case,
)
from src.presentation.schemas.firma_schemas import FirmaDigitalResponse

router = APIRouter(
    prefix="/cotizaciones/{cotizacion_id}/firma-digital", tags=["Firma digital"]
)

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_STATUS_FIRMA = {
    "FORMATO_NO_SOPORTADO": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "FIRMA_DEMASIADO_GRANDE": status.HTTP_413_CONTENT_TOO_LARGE,
    "FIRMA_VACIA": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _error(status_code: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"codigo": codigo, "mensaje": mensaje})


async def _leer_firma(archivos: list[UploadFile] | None) -> ArchivoFirma:
    if not archivos or len(archivos) != 1:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "FIRMA_CANTIDAD_INVALIDA",
            "Se requiere exactamente un archivo de firma.",
        )
    upload = archivos[0]
    # Lectura acotada: nunca se carga más del máximo permitido + 1 byte.
    contenido = await upload.read(settings.FIRMA_MAX_BYTES + 1)
    return ArchivoFirma(
        contenido=contenido,
        content_type=(upload.content_type or "").split(";")[0].strip().lower(),
    )


@router.post("", response_model=FirmaDigitalResponse, status_code=status.HTTP_201_CREATED)
async def capturar_firma_digital(
    cotizacion_id: uuid.UUID,
    response: Response,
    cliente_id: uuid.UUID = Form(...),
    producto_id: uuid.UUID = Form(...),
    firma: list[UploadFile] | None = File(None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: CapturarFirmaDigitalUseCase = Depends(get_capturar_firma_digital_use_case),
) -> FirmaDigitalResponse:
    if idempotency_key is None or not _IDEMPOTENCY_KEY.match(idempotency_key):
        raise _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "IDEMPOTENCY_KEY_INVALIDA",
            "Se requiere una clave de idempotencia válida (Idempotency-Key).",
        )
    archivo = await _leer_firma(firma)
    try:
        resultado = await use_case.ejecutar(
            cliente_id,
            cotizacion_id,
            producto_id,
            archivo,
            idempotency_key,
            correlation_id or str(uuid4()),
        )
    except FirmaInvalidaError as exc:
        raise _error(
            _STATUS_FIRMA.get(exc.codigo, status.HTTP_422_UNPROCESSABLE_CONTENT),
            exc.codigo,
            exc.mensaje,
        ) from exc
    except IdempotencyKeyReutilizadaError as exc:
        raise _error(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUTILIZADA", str(exc)) from exc
    except FirmaYaVinculadaError as exc:
        raise _error(status.HTTP_409_CONFLICT, "FIRMA_YA_VINCULADA", str(exc)) from exc
    except FirmaConcurrenteError as exc:
        raise _error(status.HTTP_409_CONFLICT, "FIRMA_EN_PROCESO", str(exc)) from exc
    except AlmacenamientoFirmaError as exc:
        raise _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ALMACENAMIENTO_NO_DISPONIBLE",
            "No se pudo almacenar la firma.",
        ) from exc
    if not resultado.creada:
        response.status_code = status.HTTP_200_OK
    return FirmaDigitalResponse.model_validate(resultado.firma)


@router.get("", response_model=FirmaDigitalResponse)
async def consultar_firma_digital(
    cotizacion_id: uuid.UUID,
    use_case: ConsultarFirmaDigitalUseCase = Depends(get_consultar_firma_digital_use_case),
) -> FirmaDigitalResponse:
    try:
        firma = await use_case.ejecutar(cotizacion_id)
    except FirmaNoEncontradaError as exc:
        raise _error(
            status.HTTP_404_NOT_FOUND, "FIRMA_NO_ENCONTRADA", str(exc)
        ) from exc
    return FirmaDigitalResponse.model_validate(firma)
