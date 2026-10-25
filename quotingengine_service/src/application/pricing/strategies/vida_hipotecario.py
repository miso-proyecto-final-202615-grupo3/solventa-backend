import logging
import uuid

from src.application.ports.perfil_cliente_gateway import (
    ConsentimientoNoOtorgadoError,
    PerfilClienteGateway,
    PerfilNoDisponibleError,
)
from src.application.pricing.strategies.tasa_base import TasaBasePricingStrategy
from src.application.pricing.strategy import SenalesPricing

logger = logging.getLogger(__name__)

DEGRADACION_SIN_CONSENTIMIENTO = "PERFIL_SIN_CONSENTIMIENTO"
DEGRADACION_PERFIL_NO_DISPONIBLE = "PERFIL_NO_DISPONIBLE"


class VidaHipotecarioPricingStrategy(TasaBasePricingStrategy):
    """Seguro de vida hipotecario.

    Consulta el perfil del cliente en identity_service (gRPC). Si el servicio no
    responde o el cliente no dio consentimiento, continúa sin personalizar.
    El cálculo con factores Open Finance / Open Data se implementa en HU1.2.4.
    """

    codigo_producto = "VIDA_HIPOTECARIO"

    def __init__(self, perfil_gateway: PerfilClienteGateway) -> None:
        self._perfil_gateway = perfil_gateway

    async def recolectar_senales(self, cliente_id: uuid.UUID) -> SenalesPricing:
        try:
            perfil = await self._perfil_gateway.obtener_perfil(cliente_id)
        except ConsentimientoNoOtorgadoError:
            return SenalesPricing(degradaciones=(DEGRADACION_SIN_CONSENTIMIENTO,))
        except PerfilNoDisponibleError:
            logger.warning("Perfil del cliente %s no disponible; se cotiza sin personalizar", cliente_id)
            return SenalesPricing(degradaciones=(DEGRADACION_PERFIL_NO_DISPONIBLE,))
        return SenalesPricing(perfil=perfil)
