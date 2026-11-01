"""Adaptador de liveness: contrato normalizado, sin datos de cliente ni evidencia persistida.

Patrones del experimento HA12: cada proveedor es una estrategia (`LivenessProvider`), la fábrica
las registra y el proveedor activo se cambia en caliente con `PUT /admin/liveness-provider`.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, File, Form, Header, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from starlette.concurrency import run_in_threadpool

from src.application.ports import (
    LivenessProvider,
    ProviderNotRegisteredError,
    ProviderUnavailableError,
)
from src.core.config import settings
from src.infrastructure.budget import ProviderBudget
from src.infrastructure.configuration import RedisActiveProviderConfiguration
from src.infrastructure.provider_factory import LivenessProviderFactory
from src.infrastructure.providers.didit import DiditProvider
from src.infrastructure.providers.propio import PropioProvider
from src.infrastructure.session_store import RedisLivenessSessionStore

logger = logging.getLogger("uvicorn.error")

_providers_warm = asyncio.Event()


async def warm_up_providers() -> None:
    """Precarga los modelos de las estrategias; `/ready` no responde 200 hasta terminar."""
    for name in _factory.registered():
        warm_up = getattr(_factory.get(name), "warm_up", None)
        if warm_up is None:
            continue
        try:
            await run_in_threadpool(warm_up)
        except Exception:
            logger.exception("liveness_provider_warm_up_failed liveness_provider=%s", name)
            return
    _providers_warm.set()
    logger.info("liveness_providers_ready providers=%s", ",".join(_factory.registered()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # En segundo plano: /health responde mientras carga, así la liveness probe no reinicia el pod.
    task = asyncio.create_task(warm_up_providers())
    yield
    task.cancel()


app = FastAPI(title="Solventa Liveness Adapter", version="0.1.0", lifespan=lifespan)
_factory = LivenessProviderFactory(
    [PropioProvider()] + ([DiditProvider()] if settings.DIDIT_ENABLED else [])
)
_redis = Redis.from_url(settings.REDIS_ENDPOINT, password=settings.REDIS_AUTH_TOKEN or None)
_active_provider = RedisActiveProviderConfiguration(_redis, settings.LIVENESS_PROVIDER)
_session_store = RedisLivenessSessionStore(_redis, settings.LIVENESS_SESSION_TTL_SECONDS)
_budget = ProviderBudget(_redis, settings.DIDIT_MAX_SESIONES_DIA, settings.DIDIT_MAX_SESIONES_MES)

_FALLBACK_PROVIDER = "propio"
_FRAME_NAMES = ("frame_inicio", "frame_gesto", "frame_fin")


def _unavailable(exc: Exception | None = None) -> HTTPException:
    return HTTPException(503, detail={"codigo": "SERVICIO_NO_DISPONIBLE"})


async def _save_session(session_id: str, session: dict) -> None:
    try:
        await _session_store.save(session_id, session)
    except Exception as exc:
        logger.error("liveness_session_store_unavailable session_id=%s", session_id)
        raise _unavailable() from exc


async def _get_session(session_id: str) -> dict | None:
    try:
        return await _session_store.get(session_id)
    except Exception as exc:
        logger.error("liveness_session_store_unavailable session_id=%s", session_id)
        raise _unavailable() from exc


async def _transition(session_id: str, expected: str, target: str) -> bool:
    """Cambio atómico de estado; si Redis falla no hay respaldo que reabra la carrera."""
    try:
        return await _session_store.transition(session_id, expected, target)
    except Exception as exc:
        logger.error("liveness_session_store_unavailable session_id=%s", session_id)
        raise _unavailable() from exc


async def _active_provider_name() -> str:
    try:
        return await _active_provider.get_active_provider_async()
    except RuntimeError as exc:
        raise _unavailable() from exc


class StartRequest(BaseModel):
    customer_id: str = Field(min_length=1)


class ActiveProviderRequest(BaseModel):
    provider: str = Field(min_length=1)


@app.get("/api/v1/liveness-adapter/health")
async def health() -> dict:
    """Vida del proceso: no depende de Redis para que Kubernetes no reinicie pods sanos."""
    return {"status": "healthy"}


@app.get("/api/v1/liveness-adapter/ready")
async def ready() -> dict:
    """Disponibilidad: modelos cargados y Redis, obligatorio para sesiones compartidas entre pods."""
    if not _providers_warm.is_set():
        raise _unavailable()
    try:
        await _redis.ping()
    except Exception as exc:
        raise _unavailable() from exc
    return {"status": "ready"}


@app.post("/api/v1/liveness-adapter/liveness/sessions", status_code=status.HTTP_201_CREATED)
async def start_session(payload: StartRequest, x_correlation_id: str | None = Header(None)) -> dict:
    correlation_id = x_correlation_id or str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    provider_name = await _active_provider_name()
    try:
        provider = _factory.get(provider_name)
    except ProviderNotRegisteredError:
        logger.warning(
            "liveness_provider_not_registered provider=%s correlation_id=%s", provider_name, correlation_id
        )
        provider = _factory.get(_FALLBACK_PROVIDER)

    started = None
    if provider.requires_budget and not await _budget.consume(provider.name):
        logger.warning("liveness_provider_fallback=quota provider=%s correlation_id=%s", provider.name, correlation_id)
    else:
        try:
            started = await run_in_threadpool(provider.start_session, payload.customer_id, session_id)
        except ProviderUnavailableError:
            if provider.name == _FALLBACK_PROVIDER:
                raise HTTPException(502, detail={"codigo": "PROVEEDOR_NO_DISPONIBLE"})
            logger.warning(
                "liveness_provider_fallback=unavailable provider=%s correlation_id=%s", provider.name, correlation_id
            )
    if started is None:
        provider = _factory.get(_FALLBACK_PROVIDER)
        started = await run_in_threadpool(provider.start_session, payload.customer_id, session_id)

    capture = started.capture
    nonce = capture.get("reto", {}).get("nonce") if capture.get("tipo") == "FRAMES" else None
    if capture.get("tipo") == "FRAMES" and not isinstance(nonce, str):
        raise HTTPException(502, detail={"codigo": "PROVEEDOR_NO_DISPONIBLE"})

    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(seconds=settings.LIVENESS_SESSION_TTL_SECONDS)
    await _save_session(
        session_id,
        {
            "customer_id": payload.customer_id,
            "nonce_hash": hashlib.sha256(nonce.encode()).hexdigest() if nonce else None,
            "expires_at": expires_at,
            "created_at": created_at,
            "state": "CREATED",
            "provider": provider.name,
            "capture_type": capture.get("tipo"),
            "gesture": capture.get("reto", {}).get("gesto"),
            "provider_session_id": started.provider_session_id,
        },
    )
    logger.info(
        "liveness_session_started liveness_provider=%s correlation_id=%s session_id=%s capture=%s",
        provider.name, correlation_id, session_id, capture.get("tipo"),
    )
    return {
        "session_id": session_id,
        "expires_at": expires_at.isoformat(),
        "capture": capture,
        "correlation_id": correlation_id,
    }


@app.post(
    "/api/v1/liveness-adapter/liveness/sessions/{session_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_session(session_id: str, x_correlation_id: str | None = Header(None)) -> Response:
    """Invalida un reto no usado; cancelar dos veces es seguro."""
    session = await _get_session(session_id)
    if session is None:
        raise HTTPException(404, detail={"codigo": "SESION_NO_ENCONTRADA"})
    if session["state"] == "CANCELLED":
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not await _transition(session_id, "CREATED", "CANCELLED"):
        refreshed = await _get_session(session_id)
        if refreshed is not None and refreshed["state"] == "CANCELLED":
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
    logger.info("liveness_session_cancelled correlation_id=%s session_id=%s", x_correlation_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _parse_timestamps(data: dict, session: dict) -> None:
    try:
        timestamps = [
            datetime.fromisoformat(data["capturas"][name].replace("Z", "+00:00"))
            for name in ("inicio", "gesto", "fin")
        ]
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(422, detail={"codigo": "DATOS_INVALIDOS"}) from exc
    duration = (timestamps[-1] - timestamps[0]).total_seconds()
    if (
        timestamps != sorted(timestamps)
        or timestamps[0] < session["created_at"]
        or timestamps[-1] > session["expires_at"]
        or not settings.PROPIO_MIN_DURATION_SECONDS <= duration <= settings.PROPIO_MAX_DURATION_SECONDS
    ):
        raise HTTPException(422, detail={"codigo": "CAPTURA_INVALIDA"})


async def _read_frames(uploads: dict[str, UploadFile | None]) -> dict[str, bytes]:
    frames: dict[str, bytes] = {}
    for name, upload in uploads.items():
        if upload is None:
            raise HTTPException(422, detail={"codigo": "DATOS_INVALIDOS"})
        content = await upload.read(settings.MAX_FRAME_BYTES + 1)
        if len(content) > settings.MAX_FRAME_BYTES:
            raise HTTPException(413, detail={"codigo": "CAPTURA_DEMASIADO_GRANDE"})
        if upload.content_type != "image/jpeg" or not content.startswith(b"\xff\xd8\xff"):
            raise HTTPException(415, detail={"codigo": "FORMATO_NO_SOPORTADO"})
        frames[name] = content
    return frames


@app.post("/api/v1/liveness-adapter/liveness/verifications")
async def verify_session(
    metadata: str = Form(...),
    frame_inicio: UploadFile | None = File(None),
    frame_gesto: UploadFile | None = File(None),
    frame_fin: UploadFile | None = File(None),
    x_correlation_id: str | None = Header(None),
) -> dict:
    correlation_id = x_correlation_id or str(uuid.uuid4())
    try:
        data = json.loads(metadata)
        session_id = data["session_id"]
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(422, detail={"codigo": "DATOS_INVALIDOS"}) from exc
    session = await _get_session(session_id)
    if session is None or data.get("customer_id") != session["customer_id"]:
        raise HTTPException(404, detail={"codigo": "SESION_NO_ENCONTRADA"})
    if session["state"] != "CREATED" or session["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})

    frames: dict[str, bytes] = {}
    sdk_result = None
    if session.get("capture_type", "FRAMES") == "FRAMES":
        nonce = str(data.get("nonce", ""))
        if not hmac.compare_digest(hashlib.sha256(nonce.encode()).hexdigest(), session["nonce_hash"] or ""):
            raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
        _parse_timestamps(data, session)
        frames = await _read_frames(
            {"frame_inicio": frame_inicio, "frame_gesto": frame_gesto, "frame_fin": frame_fin}
        )
    else:
        sdk_result = data.get("resultado_sdk")
        if sdk_result not in {"COMPLETED", "CANCELLED", "FAILED"}:
            raise HTTPException(422, detail={"codigo": "DATOS_INVALIDOS"})
        if sdk_result == "CANCELLED":
            if not await _transition(session_id, "CREATED", "CANCELLED"):
                raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})
            raise HTTPException(409, detail={"codigo": "SESION_CANCELADA"})

    if not await _transition(session_id, "CREATED", "VERIFYING"):
        raise HTTPException(409, detail={"codigo": "SESION_INVALIDA"})

    try:
        provider: LivenessProvider = _factory.get(session["provider"])
        result = await run_in_threadpool(provider.verify, session, frames, sdk_result)
    except (ProviderNotRegisteredError, ProviderUnavailableError) as exc:
        # FRAMES: el reto no se reenvía (D11). SDK: la decisión de Didit puede llegar después.
        target = "CANCELLED" if session.get("capture_type", "FRAMES") == "FRAMES" else "CREATED"
        await _transition(session_id, "VERIFYING", target)
        logger.warning(
            "liveness_verification_unavailable liveness_provider=%s correlation_id=%s session_id=%s",
            session["provider"], correlation_id, session_id,
        )
        raise HTTPException(502, detail={"codigo": "PROVEEDOR_NO_DISPONIBLE"}) from exc
    finally:
        frames.clear()

    await _transition(session_id, "VERIFYING", "USED")
    verification_id = result.verification_id or f"{session['provider']}-{uuid.uuid4()}"
    status_value = "approved" if result.approved else "rejected"
    logger.info(
        "liveness_verification liveness_provider=%s correlation_id=%s session_id=%s status=%s reason=%s",
        session["provider"], correlation_id, session_id, status_value, result.reason,
    )
    return {
        "verification_id": verification_id,
        "status": status_value,
        "reason": result.reason,
        "correlation_id": correlation_id,
    }


def _require_admin_token(token: str | None) -> None:
    if not settings.ADMIN_TOKEN or token is None or not hmac.compare_digest(token, settings.ADMIN_TOKEN):
        raise HTTPException(403, detail={"codigo": "NO_AUTORIZADO"})


@app.get("/api/v1/liveness-adapter/admin/liveness-provider")
async def get_active_provider(x_admin_token: str | None = Header(None)) -> dict:
    _require_admin_token(x_admin_token)
    return {"provider": await _active_provider_name(), "registered": list(_factory.registered())}


@app.put("/api/v1/liveness-adapter/admin/liveness-provider")
async def change_active_provider(
    payload: ActiveProviderRequest, x_admin_token: str | None = Header(None)
) -> dict:
    _require_admin_token(x_admin_token)
    try:
        _factory.get(payload.provider)
    except ProviderNotRegisteredError as exc:
        raise HTTPException(422, detail={"codigo": "PROVEEDOR_NO_REGISTRADO"}) from exc
    try:
        await _active_provider.set_active_provider_async(payload.provider)
    except RuntimeError as exc:
        raise _unavailable() from exc
    logger.info("liveness_active_provider_changed liveness_provider=%s", payload.provider)
    return {"provider": payload.provider}
