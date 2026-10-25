"""
Rate limits shared by every API worker process (Redis), with an in-memory fallback for tests or when
Redis is unreachable. Fixed windows: a key may be hit `limit` times per `window_seconds`.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_memory: Dict[str, List[float]] = defaultdict(list)
_redis = None
_redis_failed = False


def reset_memory() -> None:
    """Tests: forget every in-memory counter."""
    _memory.clear()


async def _client():
    global _redis, _redis_failed
    if settings.RATE_LIMIT_BACKEND != "redis" or _redis_failed:
        return None
    if _redis is None:
        import redis.asyncio as redis_async
        _redis = redis_async.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
    return _redis


def client_ip(request: Request) -> str:
    # Behind Caddy, uvicorn's --proxy-headers sets request.client from X-Forwarded-For
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name, self.limit, self.window = name, limit, window_seconds

    def _key(self, key: str) -> str:
        return f"ratelimit:{self.name}:{key}"

    async def _redis_call(self, fn):
        global _redis_failed
        client = await _client()
        if client is None:
            return None
        try:
            return await fn(client)
        except Exception as e:  # Redis down: degrade to per-process limits rather than fail requests
            if not _redis_failed:
                logger.warning(f"Rate limiter falling back to memory: {e}")
            _redis_failed = True
            return None

    def _memory_count(self, key: str) -> List[float]:
        cutoff = time.monotonic() - self.window
        hits = [t for t in _memory[self._key(key)] if t > cutoff]
        _memory[self._key(key)] = hits
        return hits

    async def count(self, key: str) -> int:
        async def get(r):
            value = await r.get(self._key(key))
            return int(value or 0)
        result = await self._redis_call(get)
        return result if result is not None else len(self._memory_count(key))

    async def hit(self, key: str) -> int:
        async def incr(r):
            k = self._key(key)
            value = await r.incr(k)
            if value == 1:
                await r.expire(k, self.window)
            return int(value)
        result = await self._redis_call(incr)
        if result is not None:
            return result
        hits = self._memory_count(key)
        hits.append(time.monotonic())
        return len(hits)

    async def reset(self, key: str) -> None:
        async def delete(r):
            await r.delete(self._key(key))
            return True
        if await self._redis_call(delete) is None:
            _memory.pop(self._key(key), None)

    async def limited(self, key: str) -> bool:
        return await self.count(key) >= self.limit

    async def enforce(self, key: str, detail: Optional[str] = None) -> None:
        """Counts this request; raises 429 once the key is over its limit."""
        if await self.hit(key) > self.limit:
            raise too_many(detail)


def too_many(detail: Optional[str] = None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail or "Too many requests. Please wait a little and try again.",
    )


# Limits (per key, per window)
login_failures = RateLimiter("login-fail", limit=10, window_seconds=15 * 60)
registrations = RateLimiter("register", limit=10, window_seconds=3600)
guest_accounts = RateLimiter("guest", limit=20, window_seconds=3600)
password_changes = RateLimiter("password", limit=10, window_seconds=3600)
uploads = RateLimiter("upload", limit=60, window_seconds=3600)
stylist_requests = RateLimiter("stylist", limit=60, window_seconds=3600)
