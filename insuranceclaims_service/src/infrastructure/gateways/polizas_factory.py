from src.core.config import Settings
from src.infrastructure.gateways.http_polizas_client import HttpPolizasClient
from src.infrastructure.gateways.polizas_en_memoria import PolizasEnMemoria

_en_memoria: PolizasEnMemoria | None = None


def crear_polizas_port(settings: Settings) -> HttpPolizasClient | PolizasEnMemoria:
    """Elige el adaptador por configuración (táctica: diferir el enlace)."""
    global _en_memoria
    if settings.POLIZAS_ADAPTER.lower() == "memoria":
        # Una sola instancia por proceso para que los `poliza_id` asignados se mantengan entre requests.
        if _en_memoria is None:
            _en_memoria = PolizasEnMemoria.desde_archivo(settings.POLIZAS_SEMILLA_PATH or None)
        return _en_memoria
    return HttpPolizasClient(settings.INSURANCEPOLICIES_SERVICE_URL, settings.POLIZAS_TIMEOUT_SECONDS)
