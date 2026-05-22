"""In-memory sliding-window rate limiter.

Состояние держится в памяти процесса. Деплой ограничен одним воркером
(см. core/ws.py и Dockerfile), поэтому межпроцессная синхронизация не нужна.
При переезде на multi-worker — поднимать Redis-backed реализацию.
"""
import asyncio
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import PlainTextResponse, Response


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


LOGIN_LIMIT = RateLimit(limit=10, window_seconds=60)
REGISTER_LIMIT = RateLimit(limit=5, window_seconds=3600)
OWNER_REGISTER_LIMIT = RateLimit(limit=3, window_seconds=3600)
PAYMENT_LIMIT = RateLimit(limit=10, window_seconds=60)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, config: RateLimit) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - config.window_seconds
        async with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= config.limit:
                retry_after = max(1, int(hits[0] + config.window_seconds - now) + 1)
                return False, retry_after
            hits.append(now)
            return True, 0

    def reset(self) -> None:
        self._hits.clear()


limiter = InMemoryRateLimiter()


def client_ip(request: Request) -> str:
    # Сознательно не доверяем X-Forwarded-For без явной настройки доверенного прокси.
    if request.client:
        return request.client.host
    return "unknown"


async def enforce_rate_limit(
    request: Request,
    bucket: str,
    config: RateLimit,
    *,
    key_suffix: str | None = None,
) -> Response | None:
    key = f"{bucket}:{client_ip(request)}"
    if key_suffix:
        key = f"{key}:{key_suffix}"
    ok, retry_after = await limiter.check(key, config)
    if ok:
        return None
    return PlainTextResponse(
        "Слишком много запросов. Попробуйте позже.",
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )
