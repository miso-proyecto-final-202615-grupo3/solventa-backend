from collections.abc import Iterable

from src.application.pricing.strategy import PricingStrategy


class EstrategiaNoRegistradaError(Exception):
    pass


class PricingStrategyRegistry:
    def __init__(self, strategies: Iterable[PricingStrategy]) -> None:
        self._strategies = {s.codigo_producto: s for s in strategies}

    def obtener(self, codigo_producto: str) -> PricingStrategy:
        try:
            return self._strategies[codigo_producto]
        except KeyError:
            raise EstrategiaNoRegistradaError(codigo_producto) from None
