class InMemoryActiveProviderConfiguration:
    """Configuración intercambiable; Redis la reemplazará en el despliegue distribuido."""

    def __init__(self, active_provider: str) -> None:
        self._active_provider = active_provider

    def get_active_provider(self) -> str:
        return self._active_provider

    def set_active_provider(self, provider_name: str) -> None:
        self._active_provider = provider_name
