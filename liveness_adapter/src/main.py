"""Adaptador de liveness: contrato normalizado, sin datos de cliente ni evidencia persistida."""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from src.application.ports import ProviderNotRegisteredError, ProviderUnavailableError
from src.core.config import settings
from src.infrastructure.configuration import InMemoryActiveProviderConfiguration
from src.infrastructure.provider_factory import LivenessProviderFactory
from src.infrastructure.providers.propio import PropioProvider

app = FastAPI(title="Solventa Liveness Adapter", version="0.1.0")
_sessions: dict[str, dict] = {}
_factory = LivenessProviderFactory([PropioProvider()])
_active_provider = InMemoryActiveProviderConfiguration(settings.LIVENESS_PROVIDER)


class StartRequest(BaseModel):
    customer_id: str = Field(min_length=1)


class ActiveProviderRequest(BaseModel):
    provider: str = Field(min_length=1)


@app.get("/api/v1/liveness-adapter/health")
async def health() -> dict:
    return {"status": "healthy", "provider": _active_provider.get_active_provider()}


@app.post("/api/v1/liveness-adapter/liveness/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: StartRequest, x_correlation_id: str | None = Header(None)
) -> dict:
    provider_name = _active_provider.get_active_provider()
    try:
        provider = _factory.get(provider_name)
    except ProviderNotRegisteredError as exc:
        raise HTTPException(500, detail={"codigo": "PROVEEDOR_NO_REGISTRADO"}) from exc
    started = provider.start_session()
    nonce = started.capture.get("reto", {}).get("nonce")
    if not isinstance(nonce, str):
        raise HTTPException(502, detail={"codigo": "PROVEEDOR_NO_DISPONIBLE"})
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
    _sessions[session_id] = {
        "customer_id": payload.customer_id,
        "nonce_hash": hashlib.sha256(nonce.encode()).hexdigest(),
        "expires_at": expires_at,
        "state": "CREATED",
        "provider": provider_name,
        "gesture": started.capture.get("reto", {}).get("gesto"),
    }
    return {
        "session_id": session_id,
        "expires_at": expires_at.isoformat(),
        "capture": started.capture,
        "correlation_id": x_correlation_id or str(uuid.uuid4()),
    }


@app.post(
    "/api/v1/liveness-adapter/liveness/sessions/{session_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_session(session_id: str) -> Response:
    """Invalida un reto no usado; cancelar dos veces es seguro."""
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(404, detail={"codigo": "SESION_NO_ENCONTRADA"})
    if session["state"] == "CANCELLED":
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if session["state"] != "CREATED":
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
    session["state"] = "CANCELLED"
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/liveness-adapter/liveness/verifications")
async def verify_session(
    metadata: str = Form(...),
    frame_inicio: UploadFile = File(...),
    frame_gesto: UploadFile = File(...),
    frame_fin: UploadFile = File(...),
    x_correlation_id: str | None = Header(None),
) -> dict:
    try:
        data = json.loads(metadata)
        session = _sessions[data["session_id"]]
    except (KeyError, ValueError, TypeError):
        raise HTTPException(404, detail={"codigo": "SESION_NO_ENCONTRADA"})
    if session["state"] != "CREATED" or session["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
    if data.get("customer_id") != session["customer_id"]:
        raise HTTPException(404, detail={"codigo": "SESION_NO_ENCONTRADA"})
    if hashlib.sha256(str(data.get("nonce", "")).encode()).hexdigest() != session["nonce_hash"]:
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
    frames = [frame_inicio, frame_gesto, frame_fin]
    frame_data: dict[str, bytes] = {}
    for frame in frames:
        content = await frame.read(settings.MAX_FRAME_BYTES + 1)
        if frame.content_type != "image/jpeg" or not content.startswith(b"\xff\xd8\xff"):
            raise HTTPException(415, detail={"codigo": "FORMATO_NO_SOPORTADO"})
        if len(content) > settings.MAX_FRAME_BYTES:
            raise HTTPException(413, detail={"codigo": "CAPTURA_DEMASIADO_GRANDE"})
        frame_data[frame.filename.rsplit(".", 1)[0]] = content
    try:
        provider = _factory.get(session["provider"])
    except ProviderNotRegisteredError as exc:
        raise HTTPException(500, detail={"codigo": "PROVEEDOR_NO_REGISTRADO"}) from exc
    try:
        result = provider.verify(session, frame_data)
    except ProviderUnavailableError as exc:
        session["state"] = "CANCELLED"
        raise HTTPException(502, detail={"codigo": "PROVEEDOR_NO_DISPONIBLE"}) from exc
    session["state"] = "USED"
    return {
        "verification_id": result.verification_id or f"{session['provider']}-{uuid.uuid4()}",
        "status": "approved" if result.approved else "rejected",
        "reason": result.reason,
        "correlation_id": x_correlation_id or str(uuid.uuid4()),
    }


def _require_admin_token(token: str | None) -> None:
    if not settings.ADMIN_TOKEN or token is None or not hmac.compare_digest(token, settings.ADMIN_TOKEN):
        raise HTTPException(403, detail={"codigo": "NO_AUTORIZADO"})


@app.get("/api/v1/liveness-adapter/admin/liveness-provider")
async def get_active_provider(x_admin_token: str | None = Header(None)) -> dict:
    _require_admin_token(x_admin_token)
    return {"provider": _active_provider.get_active_provider()}


@app.put("/api/v1/liveness-adapter/admin/liveness-provider")
async def change_active_provider(
    payload: ActiveProviderRequest, x_admin_token: str | None = Header(None)
) -> dict:
    _require_admin_token(x_admin_token)
    try:
        _factory.get(payload.provider)
    except ProviderNotRegisteredError as exc:
        raise HTTPException(422, detail={"codigo": "PROVEEDOR_NO_REGISTRADO"}) from exc
    _active_provider.set_active_provider(payload.provider)
    return {"provider": payload.provider}
