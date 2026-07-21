from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.core.config import settings


@dataclass
class WindowCounter:
    count: int
    reset_at: float


_lock = threading.Lock()
_windows: dict[str, WindowCounter] = {}


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

    now = time.monotonic()
    key = f"project:{project_id}:action:{action}:caller:{caller_hash(request)}"
    with _lock:
        prune_expired_windows(now)
        counter = _windows.get(key)
        if counter is None or counter.reset_at <= now:
            _windows[key] = WindowCounter(count=1, reset_at=now + window_seconds)
            return
        if counter.count >= action_limit:
            retry_after = max(1, int(counter.reset_at - now))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        counter.count += 1


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
