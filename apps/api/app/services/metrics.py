from __future__ import annotations

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.core.config import settings

HTTP_REQUESTS = Counter(
    "ai_video_editor_api_http_requests",
    "API HTTP requests by method, route, and response status.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "ai_video_editor_api_http_request_duration_seconds",
    "API HTTP request duration by method and route.",
    ("method", "route"),
)
WORKFLOW_EVENTS = Counter(
    "ai_video_editor_workflow_events",
    "Workflow lifecycle events by workflow and outcome.",
    ("workflow", "outcome"),
)
RATE_LIMIT_DECISIONS = Counter(
    "ai_video_editor_rate_limit_decisions",
    "Rate-limit decisions by backend, action, and outcome.",
    ("backend", "action", "outcome"),
)
QUOTA_DECISIONS = Counter(
    "ai_video_editor_quota_decisions",
    "Project quota decisions by metric and outcome.",
    ("metric", "outcome"),
)
RENDER_QUEUE_DEPTH = Gauge(
    "ai_video_editor_render_queue_depth",
    "Current render queue depth.",
)
DEPENDENCY_UP = Gauge(
    "ai_video_editor_dependency_up",
    "Dependency availability observed while collecting metrics.",
    ("dependency",),
)


def record_http_request(*, method: str, route: str, status_code: int, elapsed_seconds: float) -> None:
    HTTP_REQUESTS.labels(method=method, route=route, status=str(status_code)).inc()
    HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(elapsed_seconds)


def record_workflow_event(workflow: str, outcome: str) -> None:
    WORKFLOW_EVENTS.labels(workflow=workflow, outcome=outcome).inc()


def record_rate_limit_decision(*, backend: str, action: str, outcome: str) -> None:
    RATE_LIMIT_DECISIONS.labels(backend=backend, action=action, outcome=outcome).inc()


def record_quota_decision(*, metric: str, outcome: str) -> None:
    QUOTA_DECISIONS.labels(metric=metric, outcome=outcome).inc()


def render_metrics() -> tuple[bytes, str]:
    refresh_runtime_metrics()
    return generate_latest(), CONTENT_TYPE_LATEST


def refresh_runtime_metrics() -> None:
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
    if settings.rate_limit_backend == "redis":
        try:
            redis.ping()
            DEPENDENCY_UP.labels(dependency="redis_rate_limit").set(1)
        except RedisError:
            DEPENDENCY_UP.labels(dependency="redis_rate_limit").set(0)
    else:
        DEPENDENCY_UP.labels(dependency="redis_rate_limit").set(1)

    if settings.render_queue_backend == "rq":
        try:
            RENDER_QUEUE_DEPTH.set(Queue("renders", connection=redis).count)
            DEPENDENCY_UP.labels(dependency="render_queue").set(1)
        except RedisError:
            RENDER_QUEUE_DEPTH.set(0)
            DEPENDENCY_UP.labels(dependency="render_queue").set(0)
    else:
        RENDER_QUEUE_DEPTH.set(0)
        DEPENDENCY_UP.labels(dependency="render_queue").set(1)
