from collections.abc import AsyncGenerator
from uuid import UUID

import httpx
from fastapi import HTTPException, Request, Response
from starlette.datastructures import FormData
from starlette.formparsers import MultiPartException, MultiPartParser


def response_backend(response: httpx.Response) -> Response:
    headers = {}
    for name in ("content-type", "content-disposition", "cache-control"):
        if name in response.headers:
            headers[name] = response.headers[name]
    return Response(content=response.content, status_code=response.status_code, headers=headers)


def headers_backend(request: Request, cliente_id: UUID | None = None) -> dict[str, str]:
    headers = {
        key: value for key, value in request.headers.items()
        if key in {"content-type", "idempotency-key", "x-correlation-id"}
    }
    if cliente_id is not None:
        headers["X-Client-Id"] = str(cliente_id)
    return headers


async def leer_cuerpo(request: Request, limit: int) -> bytes:
    result = bytearray()
    async for chunk in request.stream():
        if len(result) + len(chunk) > limit:
            raise HTTPException(413, "Solicitud demasiado grande.")
        result.extend(chunk)
    return bytes(result)


def uuid_field(value: object, field: str) -> UUID:
    try:
        if not isinstance(value, str):
            raise ValueError
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(422, f"{field} inválido.") from exc


async def leer_multipart(request: Request, limit: int) -> tuple[bytes, FormData]:
    body = await leer_cuerpo(request, limit)

    async def stream() -> AsyncGenerator[bytes, None]:
        yield body

    try:
        form = await MultiPartParser(request.headers, stream()).parse()
    except MultiPartException as exc:
        raise HTTPException(422, "Formulario inválido.") from exc
    return body, form
