from src.application.ports import LivenessProvider, ProviderNotRegisteredError


class LivenessProviderFactory:
    """Registro central de estrategias disponibles para el adaptador."""

    def __init__(self, providers: list[LivenessProvider]) -> None:
        self._providers = {provider.name: provider for provider in providers}

    def registered(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def get(self, provider_name: str) -> LivenessProvider:
        try:
            return self._providers[provider_name]
        except KeyError as exc:
            raise ProviderNotRegisteredError(provider_name) from exc
