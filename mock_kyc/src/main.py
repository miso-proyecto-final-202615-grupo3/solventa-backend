import logging
import os
import uuid

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="Solventa Mock KYC", version="0.1.0")


@app.middleware("http")
async def log_internal_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "Error interno al procesar %s %s",
            request.method,
            request.url.path,
        )
        raise


class VerificacionIniciadaResponse(BaseModel):
    verification_id: str


class VerificacionResultadoResponse(BaseModel):
    verification_id: str
    kyc_status: str
    aml_status: str


@app.post("/verificaciones-kyc-aml", response_model=VerificacionIniciadaResponse)
def iniciar_verificacion_kyc_aml() -> VerificacionIniciadaResponse:
    # El cuerpo (documentos y referencias a S3) se descarta sin leerlo.
    return VerificacionIniciadaResponse(verification_id=str(uuid.uuid4()))


@app.get(
    "/verificaciones-kyc-aml/{verification_id}",
    response_model=VerificacionResultadoResponse,
)
def consultar_verificacion_kyc_aml(verification_id: str) -> VerificacionResultadoResponse:
    return VerificacionResultadoResponse(
        verification_id=verification_id,
        kyc_status=os.getenv("MOCK_KYC_STATUS") or "PASSED",
        aml_status=os.getenv("MOCK_AML_STATUS") or "PASSED",
    )


# --- Imitación de la API de sesiones de Didit (HU3.1.1) -------------------------------------
# Mismas rutas y formas que https://verification.didit.me para probar DiditProvider sin costo.

_DIDIT_SESSIONS: dict[str, dict] = {}
_DIDIT_DECISIONS = {"Approved", "Declined", "In Review"}


class DiditSessionRequest(BaseModel):
    workflow_id: str = Field(min_length=1)
    vendor_data: str | None = None
    metadata: dict | None = None


def _require_api_key(x_api_key: str | None) -> None:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="x-api-key requerido")


@app.post("/v3/session/", status_code=201)
def create_didit_session(
    payload: DiditSessionRequest, x_api_key: str | None = Header(default=None)
) -> dict:
    _require_api_key(x_api_key)
    session_id = str(uuid.uuid4())
    _DIDIT_SESSIONS[session_id] = {"vendor_data": payload.vendor_data, "metadata": payload.metadata}
    return {
        "session_id": session_id,
        "session_token": uuid.uuid4().hex,
        "url": f"http://mock_kyc/session/{session_id}",
        "status": "Not Started",
        "workflow_id": payload.workflow_id,
        "vendor_data": payload.vendor_data,
        "metadata": payload.metadata,
    }


@app.get("/v3/session/{session_id}/decision/")
def didit_decision(session_id: str, x_api_key: str | None = Header(default=None)) -> dict:
    _require_api_key(x_api_key)
    session = _DIDIT_SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    status_value = os.getenv("MOCK_DIDIT_STATUS", "Approved")
    if status_value not in _DIDIT_DECISIONS:
        status_value = "Approved"
    # Regla determinista para pruebas manuales: vendor_data que termina en 0 se rechaza.
    if (session.get("vendor_data") or "").endswith("0"):
        status_value = "Declined"
    return {"session_id": session_id, "status": status_value, "vendor_data": session.get("vendor_data")}
