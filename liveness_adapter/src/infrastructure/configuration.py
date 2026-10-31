class InMemoryActiveProviderConfiguration:
    """Configuración intercambiable; Redis la reemplazará en el despliegue distribuido."""

    def __init__(self, active_provider: str) -> None:
        self._active_provider = active_provider

    def get_active_provider(self) -> str:
        return self._active_provider

    def set_active_provider(self, provider_name: str) -> None:
        self._active_provider = provider_name


class RedisActiveProviderConfiguration(InMemoryActiveProviderConfiguration):
    """Persistencia del proveedor activo; conserva el último valor si Redis falla."""

    def __init__(self, redis, active_provider: str) -> None:
        super().__init__(active_provider)
        self._redis = redis

    async def get_active_provider_async(self) -> str:
        try:
            value = await self._redis.get("liveness:active_provider")
            if value:
                self._active_provider = value.decode() if isinstance(value, bytes) else value
        except Exception:
            pass
        return self._active_provider

    async def set_active_provider_async(self, provider_name: str) -> None:
        self._active_provider = provider_name
        try:
            await self._redis.set("liveness:active_provider", provider_name)
        except Exception:
            pass
