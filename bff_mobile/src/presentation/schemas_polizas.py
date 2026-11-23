"""Billetera de pólizas para la app (HU3.2.1 y HU3.2.2). Contrato en docs/contracts/polizas/."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ProductoPolizaMovil(BaseModel):
    codigo: str
    nombre: str


class CoberturaPolizaMovil(BaseModel):
    cobertura_id: uuid.UUID
    # `None` si el catálogo no conoce la cobertura (producto inactivo): la app muestra un texto genérico.
    nombre: str | None = None
    limite_asegurado: Decimal
    deducible: Decimal


class PolizaMovil(BaseModel):
    poliza_id: uuid.UUID
    numero: str
    estado: str
    ramo: str
    producto: ProductoPolizaMovil | None = None
    vigencia_desde: datetime
    vigencia_hasta: datetime
    emitida_en: datetime | None = None
    prima_total: Decimal
    coberturas: list[CoberturaPolizaMovil]


class BilleteraPolizasResponse(BaseModel):
    """Todas las pólizas del cliente (también las canceladas o vencidas, para poder reflejar su estado)."""

    polizas: list[PolizaMovil]
    sincronizado_en: datetime
