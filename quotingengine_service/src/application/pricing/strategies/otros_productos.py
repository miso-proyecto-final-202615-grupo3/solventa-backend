from src.application.pricing.strategies.tasa_base import TasaBasePricingStrategy


class ProteccionPagosPricingStrategy(TasaBasePricingStrategy):
    codigo_producto = "PROTECCION_PAGOS"


class ViajePricingStrategy(TasaBasePricingStrategy):
    codigo_producto = "SEGURO_VIAJE"


class ProteccionDispositivosPricingStrategy(TasaBasePricingStrategy):
    codigo_producto = "PROTECCION_DISPOSITIVOS"


class MicroseguroVidaPricingStrategy(TasaBasePricingStrategy):
    codigo_producto = "MICROSEGURO_VIDA"


class ParametricoPricingStrategy(TasaBasePricingStrategy):
    codigo_producto = "SEGURO_PARAMETRICO"
