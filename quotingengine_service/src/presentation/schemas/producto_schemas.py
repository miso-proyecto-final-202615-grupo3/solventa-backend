import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class CoberturaResponse(BaseModel):
    cobertura_id: uuid.UUID
    codigo: str
    nombre: str
    limite_asegurado: Decimal
    deducible: Decimal


class ParametroSeguroResponse(BaseModel):
    nombre: str
    etiqueta: str
    descripcion: str = ""
    tipo: str
    requerido: bool = True
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    unidad: str | None = None


class ProductoResponse(BaseModel):
    producto_id: uuid.UUID
    codigo: str
    nombre: str
    ramo: str
    pais: str
    estado: str
    moneda: str
    mensaje_legal: str
    fuentes_datos: list[str]
    parametros: list[ParametroSeguroResponse]
    coberturas: list[CoberturaResponse]


def producto_response(catalogo: Any) -> ProductoResponse:
    p = catalogo.producto
    return ProductoResponse(
        producto_id=p.producto_id,
        codigo=p.codigo,
        nombre=p.nombre,
        ramo=p.ramo,
        pais=p.pais,
        estado=p.estado.value,
        moneda=catalogo.moneda,
        mensaje_legal=catalogo.mensaje_legal,
        fuentes_datos=catalogo.fuentes_datos,
        parametros=[ParametroSeguroResponse(**x) for x in catalogo.parametros],
        coberturas=[
            CoberturaResponse(
                cobertura_id=c.cobertura_id,
                codigo=c.codigo,
                nombre=c.nombre,
                limite_asegurado=c.limite_asegurado,
                deducible=c.deducible,
            )
            for c in catalogo.coberturas
        ],
    )
