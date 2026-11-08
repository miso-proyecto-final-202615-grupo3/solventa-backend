import re
import uuid
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status

from src.application.ports.kyc_aml import ProveedorKycAmlError
from src.application.use_cases.consultar_verificacion_kyc_aml_use_case import (
    ConsultarVerificacionKycAmlUseCase,
    VerificacionNoEncontradaError,
    VerificacionNoIniciadaError,
)
from src.application.use_cases.iniciar_verificacion_kyc_aml_use_case import (
    ClienteKycNoEncontradoError,
    IdempotencyKeyReutilizadaError,
    IniciarVerificacionKycAmlUseCase,
    VerificacionEnProcesoError,
)
from src.core.config import settings
from src.domain.verificaciones_kyc_aml.entities import (
    ArchivoDocumento,
    DocumentoInvalidoError,
    EstadoVerificacion,
    ResultadoChequeo,
)
from src.domain.verificaciones_kyc_aml.repositories import AlmacenamientoDocumentosError
from src.presentation.dependencies import (
    get_consultar_verificacion_kyc_aml_use_case,
    get_iniciar_verificacion_kyc_aml_use_case,
)
from src.presentation.schemas import (
    EstadoResultadoVerificacion,
    EstadoValidacion,
    IniciarVerificacionKycAmlResponse,
    VerificacionKycAmlResponse,
)

router = APIRouter(
    prefix="/clientes/{cliente_id}/verificaciones-kyc-aml",
    tags=["Verificaciones KYC/AML"],
)

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_STATUS_DOCUMENTO = {
    "FORMATO_NO_SOPORTADO": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "DOCUMENTO_DEMASIADO_GRANDE": status.HTTP_413_CONTENT_TOO_LARGE,
    "DOCUMENTO_VACIO": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _error(status_code: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"codigo": codigo, "mensaje": mensaje})


async def _leer_documento(upload: UploadFile | None) -> ArchivoDocumento:
    if upload is None:
        raise _error(
            422, "DOCUMENTOS_INCOMPLETOS", "Se requieren el documento frontal y el reverso."
        )
    # Lectura acotada: nunca se carga más del máximo permitido + 1 byte.
    contenido = await upload.read(settings.KYC_DOCUMENT_MAX_BYTES + 1)
    return ArchivoDocumento(
        contenido=contenido, content_type=(upload.content_type or "").split(";")[0].strip().lower()
    )


@router.post(
    "",
    response_model=IniciarVerificacionKycAmlResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def iniciar_verificacion_kyc_aml(
    cliente_id: uuid.UUID,
    documento_frontal: UploadFile | None = File(None),
    documento_reverso: UploadFile | None = File(None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: IniciarVerificacionKycAmlUseCase = Depends(
        get_iniciar_verificacion_kyc_aml_use_case
    ),
) -> IniciarVerificacionKycAmlResponse:
    if idempotency_key is not None and not _IDEMPOTENCY_KEY.match(idempotency_key):
        raise _error(422, "IDEMPOTENCY_KEY_INVALIDA", "La clave de idempotencia no es válida.")
    frontal = await _leer_documento(documento_frontal)
    reverso = await _leer_documento(documento_reverso)
    try:
        verificacion = await use_case.ejecutar(
            cliente_id, frontal, reverso, idempotency_key, correlation_id or str(uuid4())
        )
    except DocumentoInvalidoError as exc:
        raise _error(_STATUS_DOCUMENTO.get(exc.codigo, 422), exc.codigo, exc.mensaje) from exc
    except ClienteKycNoEncontradoError as exc:
        raise _error(404, "CLIENTE_NO_ENCONTRADO", "El cliente indicado no existe.") from exc
    except IdempotencyKeyReutilizadaError as exc:
        raise _error(409, "IDEMPOTENCY_KEY_REUTILIZADA", str(exc)) from exc
    except VerificacionEnProcesoError as exc:
        raise _error(409, "VERIFICACION_EN_PROCESO", str(exc)) from exc
    except AlmacenamientoDocumentosError as exc:
        raise _error(
            503, "ALMACENAMIENTO_NO_DISPONIBLE", "No se pudieron almacenar los documentos."
        ) from exc
    except ProveedorKycAmlError as exc:
        raise _error(
            503, "PROVEEDOR_KYC_AML_NO_DISPONIBLE", "El proveedor KYC/AML no está disponible."
        ) from exc
    return IniciarVerificacionKycAmlResponse(
        verificacion_id=verificacion.id,
        estado=EstadoValidacion.INICIADA,
        fecha=verificacion.iniciada_en,
    )


def _resultado(valor: ResultadoChequeo | None) -> EstadoResultadoVerificacion:
    return EstadoResultadoVerificacion(valor.value if valor else ResultadoChequeo.PENDIENTE.value)


@router.get("/{verificacion_id}", response_model=VerificacionKycAmlResponse)
async def consultar_verificacion_kyc_aml(
    cliente_id: uuid.UUID,
    verificacion_id: uuid.UUID,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-Id"),
    use_case: ConsultarVerificacionKycAmlUseCase = Depends(
        get_consultar_verificacion_kyc_aml_use_case
    ),
) -> VerificacionKycAmlResponse:
    try:
        verificacion = await use_case.ejecutar(
            cliente_id, verificacion_id, correlation_id or str(uuid4())
        )
    except VerificacionNoEncontradaError as exc:
        raise _error(404, "VERIFICACION_NO_ENCONTRADA", "La verificación indicada no existe.") from exc
    except VerificacionNoIniciadaError as exc:
        raise _error(409, "VERIFICACION_NO_INICIADA", str(exc)) from exc
    except ProveedorKycAmlError as exc:
        raise _error(
            503, "PROVEEDOR_KYC_AML_NO_DISPONIBLE", "El proveedor KYC/AML no está disponible."
        ) from exc

    estado = {
        EstadoVerificacion.APROBADA: EstadoResultadoVerificacion.APROBADO,
        EstadoVerificacion.RECHAZADA: EstadoResultadoVerificacion.RECHAZADO,
    }.get(verificacion.estado, EstadoResultadoVerificacion.PENDIENTE)
    return VerificacionKycAmlResponse(
        verificacion_id=verificacion.id,
        cliente_id=verificacion.cliente_id,
        resultado_kyc=_resultado(verificacion.resultado_kyc),
        resultado_aml=_resultado(verificacion.resultado_aml),
        estado=estado,
        fecha_resultado=verificacion.resultado_en,
    )
