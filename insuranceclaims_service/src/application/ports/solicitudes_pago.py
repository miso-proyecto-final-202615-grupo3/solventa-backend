"""Puerto hacia Pagos y Recaudo para solicitar el pago de una indemnización (HU4.2.3, supuesto P7).

Siniestros solo solicita el pago; Pagos lo ejecuta y lo audita. Un error debe lanzarse para que el relay del
outbox reintente la solicitud ("al menos una vez"; Pagos deduplica por `clave_idempotencia`).
"""
from typing import Protocol


class SolicitudesPago(Protocol):
    async def solicitar(self, solicitud: dict, correlation_id: str) -> None: ...

    async def aclose(self) -> None: ...
