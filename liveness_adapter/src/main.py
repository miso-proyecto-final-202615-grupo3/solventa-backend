"""Adaptador de liveness: contrato normalizado, sin datos de cliente ni evidencia persistida."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

app = FastAPI(title="Solventa Liveness Adapter", version="0.1.0")
_sessions: dict[str, dict] = {}


class StartRequest(BaseModel):
    customer_id: str = Field(min_length=1)


@app.post("/api/v1/liveness-adapter/liveness/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(
    payload: StartRequest, x_correlation_id: str | None = Header(None)
) -> dict:
    nonce = secrets.token_urlsafe(24)
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
    _sessions[session_id] = {
        "customer_id": payload.customer_id,
        "nonce_hash": hashlib.sha256(nonce.encode()).hexdigest(),
        "expires_at": expires_at,
        "state": "CREATED",
    }
    return {
        "session_id": session_id,
        "expires_at": expires_at.isoformat(),
        "capture": {"type": "FRAMES", "challenge": {"gesture": "BLINK", "nonce": nonce}},
        "correlation_id": x_correlation_id or str(uuid.uuid4()),
    }


@app.post("/api/v1/liveness-adapter/liveness/verifications")
async def verify_session(
    metadata: str = Form(...),
    frame_inicio: UploadFile = File(...),
    frame_gesto: UploadFile = File(...),
    frame_fin: UploadFile = File(...),
    x_correlation_id: str | None = Header(None),
) -> dict:
    import json
    try:
        data = json.loads(metadata)
        session = _sessions[data["session_id"]]
    except (KeyError, ValueError, TypeError):
        raise HTTPException(404, detail={"codigo": "SESION_NO_ENCONTRADA"})
    if session["state"] != "CREATED" or session["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
    if hashlib.sha256(str(data.get("nonce", "")).encode()).hexdigest() != session["nonce_hash"]:
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
    frames = [frame_inicio, frame_gesto, frame_fin]
    for frame in frames:
        content = await frame.read(524289)
        if frame.content_type != "image/jpeg" or not content.startswith(b"\xff\xd8\xff"):
            raise HTTPException(415, detail={"codigo": "FORMATO_NO_SOPORTADO"})
        if len(content) > 524288:
            raise HTTPException(413, detail={"codigo": "CAPTURA_DEMASIADO_GRANDE"})
    session["state"] = "USED"
    return {"verification_id": f"propio-{uuid.uuid4()}", "status": "approved", "reason": None, "correlation_id": x_correlation_id or str(uuid.uuid4())}
