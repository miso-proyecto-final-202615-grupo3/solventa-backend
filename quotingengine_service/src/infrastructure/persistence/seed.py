"""Carga inicial: productos de seguros (temp/domain/1-productos-seguros.md),
sus coberturas y reglas de rating vigentes. Es idempotente por código de producto."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.productos.entities import Cobertura, ProductoSeguro
from src.domain.reglas_rating.entities import ReglaRating
from src.infrastructure.persistence.cobertura_repository_impl import (
    SqlAlchemyCoberturaRepository,
)
from src.infrastructure.persistence.producto_seguro_repository_impl import (
    SqlAlchemyProductoSeguroRepository,
)
from src.infrastructure.persistence.regla_rating_repository_impl import (
    SqlAlchemyReglaRatingRepository,
)

logger = logging.getLogger(__name__)

PAIS = "CO"
VERSION_REGLAS = "1.0"
_AVISO = (
    " Solventa consultará a través de {fuentes} la información necesaria para "
    "calcular la prima, únicamente con su consentimiento vigente. Si alguna fuente "
    "no está disponible, la cotización se calculará con valores por defecto. "
    "La cotización es informativa y tiene vigencia limitada."
)


def _parametro(
    nombre: str, etiqueta: str, descripcion: str, minimo: int = 1
) -> dict[str, Any]:
    return {
        "nombre": nombre,
        "etiqueta": etiqueta,
        "descripcion": descripcion,
        "tipo": "number",
        "requerido": True,
        "minimo": minimo,
        "unidad": "COP",
    }


def _regla(
    tasa_base: str,
    parametro: dict[str, Any],
    fuentes: list[str],
    descripcion_legal: str,
) -> dict[str, Any]:
    nombres_fuentes = " y ".join(
        {"OPEN_FINANCE": "Open Finance", "OPEN_DATA": "Open Data"}[f] for f in fuentes
    )
    return {
        "moneda": "COP",
        "tasa_base": tasa_base,
        "iva": "0.19",
        "parametro_monto": parametro["nombre"],
        "parametros": [parametro],
        "fuentes_datos": fuentes,
        "mensaje_legal": descripcion_legal + _AVISO.format(fuentes=nombres_fuentes),
    }


def _cob(codigo: str, nombre: str, limite: str, deducible: str = "0") -> dict[str, str]:
    return {
        "codigo": codigo,
        "nombre": nombre,
        "limite_asegurado": limite,
        "deducible": deducible,
    }


CATALOGO: list[dict[str, Any]] = [
    {
        "codigo": "VIDA_HIPOTECARIO",
        "nombre": "Seguro de vida hipotecario",
        "ramo": "VIDA",
        "coberturas": [
            _cob("FALLECIMIENTO", "Fallecimiento del asegurado", "2000000000"),
            _cob("INVALIDEZ_TOTAL", "Invalidez total y permanente", "2000000000"),
        ],
        "regla": _regla(
            "0.00025",
            _parametro(
                "valor_vivienda",
                "Valor de la vivienda",
                "Monto asegurado: valor de la vivienda o saldo del crédito hipotecario.",
            ),
            ["OPEN_FINANCE", "OPEN_DATA"],
            "Cubre la cancelación de la deuda hipotecaria restante en caso de "
            "fallecimiento o invalidez del asegurado.",
        ),
    },
    {
        "codigo": "PROTECCION_PAGOS",
        "nombre": "Seguro de protección de pagos ligada a crédito",
        "ramo": "CREDITO",
        "coberturas": [
            _cob("DESEMPLEO_INVOLUNTARIO", "Desempleo involuntario", "50000000"),
            _cob("INCAPACIDAD_TEMPORAL", "Incapacidad temporal", "50000000"),
            _cob("FALLECIMIENTO", "Fallecimiento", "50000000"),
        ],
        "regla": _regla(
            "0.0300",
            _parametro(
                "valor_cuota_mensual",
                "Valor de la cuota mensual del crédito",
                "Cuota mensual de la tarjeta o préstamo de consumo a proteger.",
            ),
            ["OPEN_FINANCE"],
            "Cubre las cuotas del crédito ante desempleo involuntario, "
            "incapacidad temporal o fallecimiento.",
        ),
    },
    {
        "codigo": "SEGURO_VIAJE",
        "nombre": "Seguro de viaje",
        "ramo": "VIAJES",
        "coberturas": [
            _cob("ASISTENCIA_MEDICA", "Asistencia médica en el extranjero", "100000000"),
            _cob("CANCELACION_VUELO", "Cancelación de vuelos", "20000000", "200000"),
            _cob("PERDIDA_EQUIPAJE", "Pérdida de equipaje", "10000000", "100000"),
        ],
        "regla": _regla(
            "0.0450",
            _parametro(
                "valor_viaje",
                "Valor total del viaje",
                "Costo total del viaje (tiquetes, alojamiento y servicios).",
            ),
            ["OPEN_DATA"],
            "Cubre imprevistos durante el desplazamiento: asistencia médica, "
            "cancelación de vuelos y pérdida de equipaje.",
        ),
    },
    {
        "codigo": "PROTECCION_DISPOSITIVOS",
        "nombre": "Seguro de protección de dispositivos",
        "ramo": "DISPOSITIVOS",
        "coberturas": [
            _cob("DANO_ACCIDENTAL", "Daño accidental", "10000000", "150000"),
            _cob("ROBO", "Robo", "10000000", "300000"),
            _cob("FALLA_FUERA_GARANTIA", "Fallas fuera de garantía", "10000000", "150000"),
        ],
        "regla": _regla(
            "0.0200",
            _parametro(
                "valor_dispositivo",
                "Valor del dispositivo",
                "Valor comercial del smartphone, laptop u otro aparato a proteger.",
            ),
            ["OPEN_DATA"],
            "Protege aparatos electrónicos frente a daños accidentales, robo "
            "o fallas fuera de garantía.",
        ),
    },
    {
        "codigo": "MICROSEGURO_VIDA",
        "nombre": "Microseguro de vida",
        "ramo": "VIDA",
        "coberturas": [
            _cob("FALLECIMIENTO", "Fallecimiento", "20000000"),
            _cob("AUXILIO_FUNERARIO", "Auxilio funerario", "3000000"),
        ],
        "regla": _regla(
            "0.0008",
            _parametro(
                "suma_asegurada",
                "Suma asegurada",
                "Valor que recibirán los beneficiarios en caso de fallecimiento.",
            ),
            ["OPEN_DATA"],
            "Póliza de vida de bajo costo con primas accesibles.",
        ),
    },
    {
        "codigo": "SEGURO_PARAMETRICO",
        "nombre": "Seguro paramétrico (clima/vuelos)",
        "ramo": "PARAMETRICO",
        "coberturas": [
            _cob("LLUVIA_EXTREMA", "Evento climático: lluvia por encima del umbral", "30000000"),
            _cob("RETRASO_VUELO", "Retraso de vuelo superior al umbral", "5000000"),
        ],
        "regla": _regla(
            "0.0100",
            _parametro(
                "monto_compensacion",
                "Monto de compensación",
                "Valor que se paga automáticamente cuando ocurre el evento definido.",
            ),
            ["OPEN_DATA"],
            "Paga una compensación automática cuando ocurre un evento predefinido "
            "(p. ej. milímetros de lluvia o retraso de vuelo), sin demostrar pérdidas.",
        ),
    },
]


async def sembrar_catalogo(session: AsyncSession) -> int:
    """Crea los productos faltantes con coberturas y regla de rating. Retorna cuántos creó."""
    productos = SqlAlchemyProductoSeguroRepository(session)
    coberturas = SqlAlchemyCoberturaRepository(session)
    reglas = SqlAlchemyReglaRatingRepository(session)
    creados = 0
    for item in CATALOGO:
        if await productos.obtener_por_codigo(item["codigo"]) is not None:
            continue
        producto = await productos.guardar(
            ProductoSeguro(
                codigo=item["codigo"],
                nombre=item["nombre"],
                ramo=item["ramo"],
                pais=PAIS,
            )
        )
        for c in item["coberturas"]:
            await coberturas.guardar(
                Cobertura(
                    producto_id=producto.producto_id,
                    codigo=c["codigo"],
                    nombre=c["nombre"],
                    limite_asegurado=Decimal(c["limite_asegurado"]),
                    deducible=Decimal(c["deducible"]),
                )
            )
        await reglas.guardar(
            ReglaRating(
                producto_id=producto.producto_id,
                version=VERSION_REGLAS,
                definicion=item["regla"],
                vigente_desde=datetime.now(timezone.utc),
            )
        )
        creados += 1
    await session.commit()
    return creados
