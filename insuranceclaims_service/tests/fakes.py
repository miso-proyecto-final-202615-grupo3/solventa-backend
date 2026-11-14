"""Datos y dobles compartidos por las pruebas de siniestros."""
import uuid
from datetime import UTC, date, datetime

from src.application.ports.polizas import PolizaResumen, PolizasNoDisponibles

CLIENTE = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTRO_CLIENTE = uuid.UUID("22222222-2222-4222-8222-222222222222")
AHORA = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)


def poliza(**cambios) -> PolizaResumen:
    datos = {
        "poliza_id": uuid.UUID("8d2b6c1e-4a7f-4f0e-9a51-0c6b1d9e2f10"),
        "cliente_id": CLIENTE,
        "numero": "SLV-2026-08341",
        "estado": "VIGENTE",
        "producto_codigo": "SEGURO_VIAJE",
        "producto_nombre": "Seguro de viaje",
        "vigencia_desde": date(2026, 3, 12),
        "vigencia_hasta": date(2027, 3, 12),
    }
    datos.update(cambios)
    return PolizaResumen(**datos)


class PolizasFalsas:
    def __init__(self, *polizas: PolizaResumen, caido: bool = False) -> None:
        self.polizas = {p.poliza_id: p for p in polizas}
        self.caido = caido
        self.llamadas: list[tuple[str, str]] = []

    async def listar_por_cliente(self, cliente_id, correlation_id):
        self.llamadas.append(("listar", correlation_id))
        if self.caido:
            raise PolizasNoDisponibles()
        return [p for p in self.polizas.values() if p.cliente_id == cliente_id]

    async def obtener(self, poliza_id, cliente_id, correlation_id):
        self.llamadas.append(("obtener", correlation_id))
        if self.caido:
            raise PolizasNoDisponibles()
        poliza = self.polizas.get(poliza_id)
        return poliza if poliza is not None and poliza.cliente_id == cliente_id else None

    async def aclose(self):
        return None
