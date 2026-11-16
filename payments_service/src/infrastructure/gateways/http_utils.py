from typing import Any

import httpx

from src.application.ports.servicios import ServicioNoDisponibleError


async def solicitar_json(
    client: httpx.AsyncClient,
    servicio: str,
    ruta: str,
    correlation_id: str,
    *,
    permitir_404: bool = False,
) -> dict[str, Any] | None:
    """GET con el correlation id; None si hay 404 y se permite, de lo contrario falla si no es 2xx."""
    try:
        response = await client.get(ruta, headers={"X-Correlation-Id": correlation_id})
    except httpx.HTTPError as exc:
        raise ServicioNoDisponibleError(servicio, type(exc).__name__) from exc
    if response.status_code == 404 and permitir_404:
        return None
    if not response.is_success:
        raise ServicioNoDisponibleError(servicio, f"HTTP {response.status_code}")
    try:
        cuerpo = response.json()
    except ValueError as exc:
        raise ServicioNoDisponibleError(servicio, "respuesta no es JSON") from exc
    if not isinstance(cuerpo, dict):
        raise ServicioNoDisponibleError(servicio, "respuesta inesperada")
    return cuerpo
