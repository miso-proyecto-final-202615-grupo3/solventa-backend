from decimal import ROUND_HALF_UP, Decimal

from src.application.pricing.strategy import (
    AjustePrima,
    ContextoPricing,
    ImpuestoPrima,
    PricingStrategy,
    ResultadoPricing,
    TipoAjuste,
)

_CENTAVOS = Decimal("0.01")


def redondear(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


class TasaBasePricingStrategy(PricingStrategy):
    """Prima base = tasa base (regla vigente) x monto asegurado, más IVA.

    Los factores de personalización (Open Finance / Open Data) se incorporan
    sobreescribiendo `calcular_ajustes` en cada estrategia (HU1.2.4).
    """

    def calcular_ajustes(
        self, contexto: ContextoPricing, prima_base: Decimal
    ) -> list[AjustePrima]:
        return []

    def calcular(self, contexto: ContextoPricing) -> ResultadoPricing:
        definicion = contexto.regla.definicion
        monto = Decimal(str(contexto.parametros[definicion["parametro_monto"]]))
        tasa_base = Decimal(str(definicion["tasa_base"]))
        tasa_iva = Decimal(str(definicion.get("iva", "0")))

        prima_base = redondear(tasa_base * monto)
        ajustes = self.calcular_ajustes(contexto, prima_base)
        prima_neta = prima_base + sum(
            (a.valor if a.tipo == TipoAjuste.RECARGO else -a.valor for a in ajustes),
            Decimal("0"),
        )
        impuestos = [
            ImpuestoPrima(
                concepto="IVA",
                tasa=tasa_iva,
                valor=redondear(prima_neta * tasa_iva),
            )
        ]
        return ResultadoPricing(
            prima_base=prima_base,
            ajustes=ajustes,
            impuestos=impuestos,
            prima_neta=prima_neta,
            prima_total=prima_neta + sum((i.valor for i in impuestos), Decimal("0")),
            moneda=definicion.get("moneda", "COP"),
            degradaciones=contexto.senales.degradaciones,
        )
