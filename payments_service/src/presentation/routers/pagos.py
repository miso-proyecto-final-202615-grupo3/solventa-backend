import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from src.application.ports.cotizaciones import CotizacionNoEncontradaError
from src.application.ports.proveedor_pago import DatosTarjeta, ProveedorPagoError, SolicitudInvalidaError
from src.application.ports.servicios import ServicioNoDisponibleError
from src.application.use_cases.consultar_pago_use_case import (
    ConsultarPagoUseCase,
    ConsultarResumenPagoUseCase,
)
from src.application.use_cases.procesar_pago_prima_use_case import (
    CondicionesNoAceptadasError,
    CotizacionNoVigenteError,
    FirmaRequeridaError,
    IdempotencyKeyReutilizadaError,
    PagoEnCursoError,
    PagoNoEncontradoError,
    PagoYaAprobadoError,
    ProcesarPagoPrimaUseCase,
    SolicitudPago,
)
from src.presentation.dependencies import (
    get_consultar_pago_use_case,
    get_consultar_resumen_pago_use_case,
    get_procesar_pago_prima_use_case,
)
from src.presentation.schemas.pago_schemas import (
    MetodoPagoResponse,
    PagoRequest,
    PagoResponse,
    ResumenPagoResponse,
)
from src.domain.pagos.entities import MetodoPago

router = APIRouter(tags=["Pagos"])

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def _error(status_code: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"codigo": codigo, "mensaje": mensaje})


def _servicio_no_disponible() -> HTTPException:
    return _error(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "SERVICIO_NO_DISPONIBLE",
        "Un servicio requerido para el pago no está disponible.",
    )


@router.get("/cotizaciones/{cotizacion_id}/resumen-pago", response_model=ResumenPagoResponse)
async def obtener_resumen_pago(
    cotizacion_id: uuid.UUID,
    correlation_id: str = Header(default="", alias="X-Correlation-Id"),
    use_case: ConsultarResumenPagoUseCase = Depends(get_consultar_resumen_pago_use_case),
) -> ResumenPagoResponse:
    try:
        resumen = await use_case.ejecutar(cotizacion_id, correlation_id or str(uuid.uuid4()))
    except CotizacionNoEncontradaError as exc:
        raise _error(404, "COTIZACION_NO_ENCONTRADA", "La cotización no existe.") from exc
    except CotizacionNoVigenteError as exc:
        raise _error(409, "COTIZACION_NO_VIGENTE", str(exc)) from exc
    except ServicioNoDisponibleError as exc:
        raise _servicio_no_disponible() from exc
    cotizacion = resumen.cotizacion
    return ResumenPagoResponse(
        cotizacion_id=cotizacion.cotizacion_id,
        prima_total=cotizacion.prima_total,
        moneda=cotizacion.moneda,
        expira_en=cotizacion.expira_en,
        metodos_pago=[
            MetodoPagoResponse(codigo=m, por_defecto=m == resumen.metodo_por_defecto)
            for m in resumen.metodos_pago
        ],
    )


@router.post(
    "/pagos",
    response_model=PagoResponse,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reintento idempotente: devuelve el pago ya registrado."}},
)
async def procesar_pago(
    payload: PagoRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str = Header(default="", alias="X-Correlation-Id"),
    use_case: ProcesarPagoPrimaUseCase = Depends(get_procesar_pago_prima_use_case),
) -> PagoResponse:
    if idempotency_key is None or not _IDEMPOTENCY_KEY.match(idempotency_key):
        raise _error(
            422,
            "IDEMPOTENCY_KEY_INVALIDA",
            "Se requiere una clave de idempotencia válida (Idempotency-Key).",
        )
    try:
        tarjeta = None
        if payload.metodo_pago == MetodoPago.TARJETA_CREDITO:
            assert payload.numero_tarjeta is not None
            assert payload.mes_expiracion is not None
            assert payload.anio_expiracion is not None
            assert payload.cvv is not None
            tarjeta = DatosTarjeta(
                payload.numero_tarjeta, payload.mes_expiracion, payload.anio_expiracion, payload.cvv
            )
        resultado = await use_case.ejecutar(
            SolicitudPago(
                cotizacion_id=payload.cotizacion_id,
                cliente_id=payload.cliente_id,
                metodo_pago=payload.metodo_pago,
                credencial=payload.paypal_email or "",
                tarjeta=tarjeta,
            ),
            idempotency_key,
            correlation_id or str(uuid.uuid4()),
        )
    except CotizacionNoEncontradaError as exc:
        raise _error(404, "COTIZACION_NO_ENCONTRADA", "La cotización no existe.") from exc
    except CotizacionNoVigenteError as exc:
        raise _error(409, "COTIZACION_NO_VIGENTE", str(exc)) from exc
    except CondicionesNoAceptadasError as exc:
        raise _error(409, "CONDICIONES_NO_ACEPTADAS", str(exc)) from exc
    except FirmaRequeridaError as exc:
        raise _error(409, "FIRMA_REQUERIDA", str(exc)) from exc
    except PagoYaAprobadoError as exc:
        raise _error(409, "PAGO_YA_APROBADO", str(exc)) from exc
    except PagoEnCursoError as exc:
        raise _error(409, "PAGO_EN_CURSO", str(exc)) from exc
    except IdempotencyKeyReutilizadaError as exc:
        raise _error(409, "IDEMPOTENCY_KEY_REUTILIZADA", str(exc)) from exc
    except ServicioNoDisponibleError as exc:
        raise _servicio_no_disponible() from exc
    except SolicitudInvalidaError as exc:
        raise _error(422, "SOLICITUD_INVALIDA", "La pasarela rechazó los datos de la tarjeta.") from exc
    except ProveedorPagoError as exc:
        raise _error(
            503,
            "PROVEEDOR_PAGO_NO_DISPONIBLE",
            "La pasarela de pagos no está disponible; reintente con la misma Idempotency-Key.",
        ) from exc
    if not resultado.creado:
        response.status_code = status.HTTP_200_OK
    return PagoResponse.model_validate(resultado.pago)


@router.get("/pagos/{pago_id}", response_model=PagoResponse)
async def obtener_pago(
    pago_id: uuid.UUID,
    use_case: ConsultarPagoUseCase = Depends(get_consultar_pago_use_case),
) -> PagoResponse:
    try:
        return PagoResponse.model_validate(await use_case.ejecutar(pago_id))
    except PagoNoEncontradoError as exc:
        raise _error(404, "PAGO_NO_ENCONTRADO", "El pago no existe.") from exc
