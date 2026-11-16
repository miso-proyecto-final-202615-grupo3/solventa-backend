import logging
import re
import time
import uuid

HEADER = b"x-correlation-id"
_VALID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_SKIP_SUFFIXES = ("/health", "/ready")


class CorrelationIdMiddleware:
    def __init__(self, app, service: str, logger_name: str = "uvicorn.error") -> None:
        self.app = app
        self.service = service
        self.logger = logging.getLogger(logger_name)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        received = next((value.decode("latin-1") for key, value in headers if key.lower() == HEADER), None)
        correlation_id = received if received and _VALID.match(received) else str(uuid.uuid4())
        if received != correlation_id:
            headers = [(key, value) for key, value in headers if key.lower() != HEADER]
            headers.append((HEADER, correlation_id.encode("latin-1")))
            scope = {**scope, "headers": headers}

        status_code = 500

        async def send_with_header(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != HEADER]
                response_headers.append((HEADER, correlation_id.encode("latin-1")))
                message = {**message, "headers": response_headers}
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_with_header)
        finally:
            path = scope.get("path", "")
            if not path.endswith(_SKIP_SUFFIXES):
                self.logger.info(
                    "%s_request method=%s path=%s status=%s duration_ms=%d correlation_id=%s",
                    self.service, scope.get("method"), path, status_code,
                    (time.perf_counter() - started) * 1000, correlation_id,
                )
