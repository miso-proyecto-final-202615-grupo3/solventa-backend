"""Adaptador de pólizas en memoria: excepción transitoria (decisión S6) hasta que MS Pólizas
exponga el endpoint interno (#265). Solo para desarrollo y demos; se activa con `POLIZAS_ADAPTER=memoria`.

Las pólizas con `cliente_id = "*"` se asignan a cada cliente que las consulta, con un `poliza_id`
estable por cliente (UUID v5), para que cualquier cuenta de Cognito pueda probar el flujo.
"""
import json
import uuid
from datetime import date
from pathlib import Path

from src.application.ports.polizas import PolizaResumen

SEMILLA_POR_DEFECTO = Path(__file__).with_name("polizas_semilla.json")
CUALQUIER_CLIENTE = "*"


class PolizasEnMemoria:
    def __init__(self, polizas: list[dict]) -> None:
        self._plantillas = polizas
        self._por_id: dict[uuid.UUID, PolizaResumen] = {}
        for plantilla in polizas:
            if plantilla.get("cliente_id", CUALQUIER_CLIENTE) != CUALQUIER_CLIENTE:
                self._registrar(self._crear(plantilla, uuid.UUID(plantilla["cliente_id"])))

    @classmethod
    def desde_archivo(cls, ruta: str | Path | None = None) -> "PolizasEnMemoria":
        datos = json.loads(Path(ruta or SEMILLA_POR_DEFECTO).read_text(encoding="utf-8"))
        return cls(datos["polizas"])

    async def listar_por_cliente(self, cliente_id: uuid.UUID, correlation_id: str) -> list[PolizaResumen]:
        for plantilla in self._plantillas:
            if plantilla.get("cliente_id", CUALQUIER_CLIENTE) == CUALQUIER_CLIENTE:
                self._registrar(self._crear(plantilla, cliente_id))
        return [p for p in self._por_id.values() if p.cliente_id == cliente_id]

    async def obtener(self, poliza_id: uuid.UUID, cliente_id: uuid.UUID, correlation_id: str) -> PolizaResumen | None:
        poliza = self._por_id.get(poliza_id)
        return poliza if poliza is not None and poliza.cliente_id == cliente_id else None

    async def aclose(self) -> None:
        return None

    def _registrar(self, poliza: PolizaResumen) -> None:
        self._por_id[poliza.poliza_id] = poliza

    @staticmethod
    def _crear(plantilla: dict, cliente_id: uuid.UUID) -> PolizaResumen:
        poliza_id = (
            uuid.UUID(plantilla["poliza_id"])
            if plantilla.get("poliza_id")
            else uuid.uuid5(cliente_id, plantilla["numero"])
        )
        return PolizaResumen(
            poliza_id=poliza_id,
            cliente_id=cliente_id,
            numero=plantilla["numero"],
            estado=plantilla["estado"],
            producto_codigo=plantilla["producto_codigo"],
            producto_nombre=plantilla["producto_nombre"],
            vigencia_desde=date.fromisoformat(plantilla["vigencia_desde"]),
            vigencia_hasta=date.fromisoformat(plantilla["vigencia_hasta"]),
        )
