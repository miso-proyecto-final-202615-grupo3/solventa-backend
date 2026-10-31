import json
from datetime import datetime


class RedisLivenessSessionStore:
    """Sesiones técnicas con TTL; no persiste frames ni nonce en claro."""

    def __init__(self, redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def save(self, session_id: str, value: dict) -> None:
        serializable = {**value, "expires_at": value["expires_at"].isoformat(), "created_at": value["created_at"].isoformat()}
        await self._redis.set(self._key(session_id), json.dumps(serializable), ex=self._ttl)

    async def get(self, session_id: str) -> dict | None:
        raw = await self._redis.get(self._key(session_id))
        if not raw:
            return None
        data = json.loads(raw)
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return data

    async def transition(self, session_id: str, expected: str, target: str) -> bool:
        key = self._key(session_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if not raw:
                        await pipe.reset()
                        return False
                    data = json.loads(raw)
                    if data.get("state") != expected:
                        await pipe.reset()
                        return False
                    data["state"] = target
                    pipe.multi()
                    pipe.set(key, json.dumps(data), keepttl=True)
                    await pipe.execute()
                    return True
                except Exception:
                    await pipe.reset()
                    raise

    @staticmethod
    def _key(session_id: str) -> str:
        return f"liveness:session:{session_id}"
