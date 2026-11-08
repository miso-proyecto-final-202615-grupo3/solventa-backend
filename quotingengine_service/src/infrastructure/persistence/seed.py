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
VERSION_CONDICIONES = "1.0"
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


def _parametro_ubicacion() -> dict[str, Any]:
    return {
        "nombre": "ubicacion",
        "etiqueta": "Ubicación de la vivienda",
        "descripcion": "Municipio, zona y estrato del inmueble asegurado.",
        "tipo": "object",
        "requerido": True,
    }


def _regla(
    tasa_base: str,
    parametro: dict[str, Any] | list[dict[str, Any]],
    fuentes: list[str],
    descripcion_legal: str,
) -> dict[str, Any]:
    nombres_fuentes = " y ".join(
        {"OPEN_FINANCE": "Open Finance", "OPEN_DATA": "Open Data"}[f] for f in fuentes
    )
    parametros = parametro if isinstance(parametro, list) else [parametro]
    parametro_monto = next(p["nombre"] for p in parametros if p["tipo"] != "object")
    return {
        "moneda": "COP",
        "tasa_base": tasa_base,
        "iva": "0.19",
        "parametro_monto": parametro_monto,
        "parametros": parametros,
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
            [
                _parametro(
                    "saldo_credito",
                    "Saldo pendiente del crédito",
                    "Monto asegurado correspondiente al saldo pendiente del crédito hipotecario.",
                ),
                _parametro_ubicacion(),
            ],
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


# Descripciones provisionales del catálogo; requieren aprobación jurídica antes de
# utilizarse como clausulado contractual.
# Textos provisionales; requieren aprobación jurídica antes de utilizarse como
# clausulado contractual. Cualquier cambio debe publicarse con una nueva versión.

_CLAUSULAS_COMUNES = (
    "DECLARACIÓN DEL RIESGO: El tomador debe declarar con sinceridad los hechos y "
    "circunstancias que determinan el estado del riesgo. La inexactitud o reticencia "
    "puede dar lugar a la nulidad relativa del contrato o a la reducción de la "
    "indemnización, conforme a la ley aplicable.\n"
    "PRIMA: El tomador debe pagar la prima en la forma y oportunidad indicadas en las "
    "condiciones particulares. La mora en el pago puede ocasionar la terminación del "
    "contrato en los términos de la ley.\n"
    "VIGENCIA Y TERMINACIÓN: La cobertura rige durante la vigencia indicada en las "
    "condiciones particulares y termina por vencimiento, por cancelación conforme a la "
    "ley, por pago de la indemnización máxima o por las causas legales aplicables. "
    "La cotización es informativa, tiene vigencia limitada y no constituye cobertura "
    "hasta la emisión de la póliza.\n"
    "AVISO Y RECLAMACIÓN: El asegurado o beneficiario debe avisar el siniestro dentro "
    "del plazo establecido en las condiciones particulares o, en su defecto, en la ley, "
    "y presentar los documentos que acrediten la ocurrencia y la cuantía de la pérdida. "
    "La aseguradora podrá solicitar información adicional razonable para evaluar la "
    "reclamación.\n"
    "FRAUDE: La presentación de información o documentos falsos en la contratación o en "
    "una reclamación libera a la aseguradora de su obligación, sin perjuicio de las "
    "acciones legales que correspondan.\n"
    "TRATAMIENTO DE DATOS: Solventa tratará los datos personales conforme a la "
    "autorización otorgada y a la política de tratamiento aplicable. La consulta de "
    "información en Open Finance u Open Data requiere consentimiento vigente y es "
    "independiente de la aceptación de estas condiciones.\n"
    "LÍMITES Y DEDUCIBLES: Los límites asegurados, deducibles y la prima total son los "
    "indicados en las condiciones particulares de la cotización aceptada."
)


def _condiciones(
    objeto: str, coberturas: str, exclusiones: str, obligaciones: str
) -> str:
    return (
        f"OBJETO: {objeto}\n"
        f"COBERTURAS: {coberturas}\n"
        f"EXCLUSIONES: {exclusiones}\n"
        f"OBLIGACIONES DEL ASEGURADO: {obligaciones}\n"
        f"{_CLAUSULAS_COMUNES}"
    )


CONDICIONES_GENERALES = {
    "VIDA_HIPOTECARIO": _condiciones(
        "Proteger al asegurado y a su familia frente a la deuda de un crédito hipotecario, "
        "pagando a la entidad acreedora, hasta el límite asegurado, el saldo pendiente "
        "cuando ocurra un evento amparado.",
        "(i) Fallecimiento del asegurado por cualquier causa no excluida; (ii) invalidez "
        "total y permanente, entendida como la pérdida de capacidad laboral en el grado "
        "definido en las condiciones particulares y debidamente calificada por la "
        "autoridad competente. La indemnización se calcula sobre el saldo del crédito "
        "reportado a la fecha del evento, sin exceder el límite asegurado.",
        "Suicidio dentro del periodo de carencia previsto en las condiciones particulares; "
        "enfermedades o condiciones preexistentes no declaradas; participación en actos "
        "delictivos; guerra, terrorismo o actividades de alto riesgo no declaradas; "
        "lesiones autoinfligidas; y saldos correspondientes a mora o intereses no "
        "cubiertos según las condiciones particulares.",
        "Mantener actualizada la información del crédito, informar cambios de la "
        "obligación hipotecaria y de su estado de salud cuando sea relevante, y colaborar "
        "con la aseguradora en la verificación del siniestro.",
    ),
    "PROTECCION_PAGOS": _condiciones(
        "Respaldar el pago de las cuotas de un crédito de consumo o tarjeta cuando el "
        "asegurado no pueda atenderlas por un evento amparado.",
        "(i) Desempleo involuntario, para asegurados con vínculo laboral dependiente "
        "debidamente acreditado; (ii) incapacidad temporal certificada por la entidad "
        "competente; (iii) fallecimiento del asegurado. La cobertura se limita al valor "
        "de las cuotas y al número máximo indicados en las condiciones particulares, sin "
        "exceder el límite asegurado.",
        "Renuncia, terminación por justa causa, vencimiento de contrato a término fijo o "
        "retiro voluntario; desempleo o incapacidad anteriores al inicio de la cobertura "
        "o dentro del periodo de carencia; trabajadores independientes en la cobertura de "
        "desempleo; incapacidades derivadas de hechos no declarados, actos delictivos o "
        "lesiones autoinfligidas; y cuotas ya vencidas antes del evento.",
        "Continuar el esfuerzo de búsqueda de empleo cuando aplique, presentar "
        "certificaciones periódicas del evento y avisar de inmediato su cese o "
        "recuperación.",
    ),
    "SEGURO_VIAJE": _condiciones(
        "Proteger al viajero frente a imprevistos ocurridos durante el viaje asegurado "
        "descrito en las condiciones particulares.",
        "(i) Asistencia médica en el extranjero por enfermedad o accidente sobrevenidos "
        "durante el viaje; (ii) cancelación de vuelos por causas amparadas, con reembolso "
        "de gastos no recuperables y sujeto a deducible; (iii) pérdida de equipaje "
        "documentada, sujeta a deducible. Cada cobertura opera hasta su límite asegurado.",
        "Enfermedades o condiciones preexistentes no declaradas; viajes contra "
        "recomendación médica; actividades deportivas de alto riesgo no contratadas; "
        "cancelaciones por decisión voluntaria sin causa amparada; objetos de valor "
        "dejados sin custodia; y destinos o eventos expresamente excluidos en las "
        "condiciones particulares.",
        "Contactar a la línea de asistencia antes de incurrir en gastos médicos, conservar "
        "facturas, tiquetes y reportes de la aerolínea o autoridad, y reportar la pérdida "
        "de equipaje ante el transportador.",
    ),
    "PROTECCION_DISPOSITIVOS": _condiciones(
        "Proteger el dispositivo electrónico identificado en las condiciones particulares "
        "frente a eventos amparados, mediante reparación, reposición o indemnización.",
        "(i) Daño accidental, como caída o contacto con líquidos; (ii) robo, con "
        "denuncia previa ante la autoridad competente; (iii) fallas fuera de garantía del "
        "fabricante. Cada evento está sujeto a deducible y no excede el límite asegurado.",
        "Desgaste normal, daños estéticos, pérdida o extravío sin robo, daños "
        "intencionales, uso indebido, modificaciones no autorizadas, fallas cubiertas por "
        "la garantía del fabricante, hurto sin violencia o sin denuncia, y dispositivos "
        "con numeración alterada.",
        "Mantener el dispositivo en uso conforme a las instrucciones del fabricante, "
        "informar sus datos de identificación, presentar la denuncia en caso de robo y "
        "permitir su inspección o peritaje.",
    ),
    "MICROSEGURO_VIDA": _condiciones(
        "Brindar protección económica básica a los beneficiarios designados mediante el "
        "pago de la suma asegurada y de un auxilio funerario cuando ocurra un evento "
        "amparado.",
        "(i) Fallecimiento del asegurado, con pago de la suma asegurada a los "
        "beneficiarios; (ii) auxilio funerario, para atender gastos exequiales hasta su "
        "límite asegurado.",
        "Suicidio dentro del periodo de carencia indicado en las condiciones particulares; "
        "fallecimiento por actos delictivos del asegurado o beneficiario, guerra, "
        "terrorismo o actividades de alto riesgo no declaradas; y eventos ocurridos antes "
        "del inicio de la cobertura.",
        "Designar y mantener actualizados los beneficiarios, informar cambios en sus datos "
        "de contacto, y presentar el registro de defunción y demás documentos solicitados.",
    ),
    "SEGURO_PARAMETRICO": _condiciones(
        "Entregar una compensación predefinida cuando un índice objetivo, como la "
        "precipitación medida o el retraso de un vuelo, alcance el umbral pactado, sin "
        "necesidad de demostrar la pérdida efectivamente sufrida.",
        "(i) Lluvia extrema, cuando la medición oficial de la fuente de datos designada, "
        "en la ubicación y periodo definidos, supere el umbral de las condiciones "
        "particulares; (ii) retraso de vuelo, cuando la fuente de datos designada "
        "registre una demora superior al umbral pactado. La compensación es la indicada "
        "en las condiciones particulares y no excede el límite asegurado.",
        "Eventos medidos fuera de la ubicación, periodo o vuelo asegurado; retrasos o "
        "lluvias que no alcancen el umbral; cancelaciones o eventos no cubiertos por el "
        "índice; y fallas de la fuente de datos, caso en el cual se aplicará la fuente "
        "alterna o el procedimiento descrito en las condiciones particulares.",
        "Verificar que la información de ubicación, fechas o vuelo sea correcta, y "
        "conservar los datos necesarios para recibir la compensación, que se determina "
        "con la fuente designada y no con la valoración de daños.",
    ),
}


async def sembrar_catalogo(session: AsyncSession) -> int:
    """Crea los productos faltantes con coberturas y regla de rating. Retorna cuántos creó."""
    productos = SqlAlchemyProductoSeguroRepository(session)
    coberturas = SqlAlchemyCoberturaRepository(session)
    reglas = SqlAlchemyReglaRatingRepository(session)
    creados = 0
    for item in CATALOGO:
        existente = await productos.obtener_por_codigo(item["codigo"])
        if existente is not None:
            await productos.inicializar_condiciones(
                existente.producto_id, CONDICIONES_GENERALES[item["codigo"]], VERSION_CONDICIONES
            )
            continue
        producto = await productos.guardar(
            ProductoSeguro(
                codigo=item["codigo"],
                nombre=item["nombre"],
                ramo=item["ramo"],
                pais=PAIS,
                condiciones_generales=CONDICIONES_GENERALES[item["codigo"]],
                version_condiciones_generales=VERSION_CONDICIONES,
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
