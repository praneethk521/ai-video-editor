from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.metrics import record_rate_limit_decision


@dataclass
class WindowCounter:
    count: int
    reset_at: float


_lock = threading.Lock()
_windows: dict[str, WindowCounter] = {}
_REDIS_FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


def enforce_project_rate_limit(
    request: Request,
    *,
    project_id: str,
    action: str,
    limit: int | None = None,
    window_seconds: int = 60,
) -> None:
    if not settings.rate_limits_enabled:
        return
    action_limit = limit if limit is not None else limit_for_action(action)
    if action_limit <= 0:
        return

    key = f"project:{project_id}:action:{action}:caller:{caller_hash(request)}"
    backend = settings.rate_limit_backend
    try:
        if backend == "redis":
            enforce_redis_window(key=key, limit=action_limit, window_seconds=window_seconds)
        else:
            enforce_memory_window(key=key, limit=action_limit, window_seconds=window_seconds)
    except HTTPException as exc:
        outcome = "limited" if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS else "backend_error"
        record_rate_limit_decision(backend=backend, action=action, outcome=outcome)
        raise
    record_rate_limit_decision(backend=backend, action=action, outcome="allowed")


def enforce_memory_window(*, key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _lock:
        prune_expired_windows(now)
        counter = _windows.get(key)
        if counter is None or counter.reset_at <= now:
            _windows[key] = WindowCounter(count=1, reset_at=now + window_seconds)
            return
        if counter.count >= limit:
            retry_after = max(1, int(counter.reset_at - now))
            raise_rate_limit_exceeded(retry_after)
        counter.count += 1


def enforce_redis_window(*, key: str, limit: int, window_seconds: int) -> None:
    redis_key = f"{settings.rate_limit_redis_prefix}:{key}"
    try:
        count, ttl = _redis_client(settings.redis_url).eval(
            _REDIS_FIXED_WINDOW_SCRIPT,
            1,
            redis_key,
            window_seconds,
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="rate limit backend unavailable",
        ) from exc
    if int(count) > limit:
        raise_rate_limit_exceeded(max(1, int(ttl)))


def raise_rate_limit_exceeded(retry_after: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="rate limit exceeded",
        headers={"Retry-After": str(retry_after)},
    )


@lru_cache(maxsize=4)
def _redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)


def limit_for_action(action: str) -> int:
    if action == "render.jobs.queue":
        return settings.render_rate_limit_per_minute
    if action.startswith("outputs.retention.cleanup"):
        return settings.retention_cleanup_rate_limit_per_minute
    return settings.expensive_workflow_rate_limit_per_minute


def caller_hash(request: Request) -> str:
    authorization = request.headers.get("authorization")
    if authorization:
        return hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:16]
    host = request.client.host if request.client else "unknown"
    return hashlib.sha256(host.encode("utf-8")).hexdigest()[:16]


def prune_expired_windows(now: float) -> None:
    expired = [key for key, counter in _windows.items() if counter.reset_at <= now]
    for key in expired:
        del _windows[key]


def reset_rate_limits() -> None:
    with _lock:
        _windows.clear()
    _redis_client.cache_clear()
