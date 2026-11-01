from datetime import datetime, timezone


class ProviderBudget:
    """Topes diario y mensual en Redis para proveedores con costo (Didit).

    Si Redis no responde, se niega el uso: es preferible caer al proveedor propio que gastar.
    """

    def __init__(self, redis, max_per_day: int, max_per_month: int) -> None:
        self._redis = redis
        self._max_per_day = max_per_day
        self._max_per_month = max_per_month

    async def consume(self, provider_name: str, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        day_key = f"liveness:{provider_name}:sessions:{now:%Y%m%d}"
        month_key = f"liveness:{provider_name}:sessions:{now:%Y%m}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(day_key)
                pipe.expire(day_key, 48 * 3600)
                pipe.incr(month_key)
                pipe.expire(month_key, 40 * 24 * 3600)
                day_count, _, month_count, _ = await pipe.execute()
        except Exception:
            return False
        return day_count <= self._max_per_day and month_count <= self._max_per_month
