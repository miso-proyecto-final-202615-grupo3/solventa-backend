import logging
import os
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

app = FastAPI(title="Solventa Mock KYC", version="0.1.0")

_VALID_STATUSES = {"PASSED", "FAILED", "PENDING"}


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


class VerifyRequest(BaseModel):
    document_type: str = Field(min_length=1)
    document_number: str = Field(min_length=1)


class VerifyResponse(BaseModel):
    verification_id: str
    status: str


@app.post("/verify", response_model=VerifyResponse)
def verify(payload: VerifyRequest) -> VerifyResponse:
    status_value = os.getenv("MOCK_KYC_STATUS", "PASSED").upper()
    if status_value not in _VALID_STATUSES:
        status_value = "PASSED"
    return VerifyResponse(
        verification_id=str(uuid.uuid4()),
        status=status_value,
    )