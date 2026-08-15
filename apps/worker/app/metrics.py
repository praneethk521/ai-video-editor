from __future__ import annotations

import os
from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Histogram, REGISTRY, multiprocess, start_http_server

from app.config import settings

RENDER_JOBS = Counter(
    "ai_video_editor_worker_render_jobs",
    "Worker render jobs by variant and outcome.",
    ("variant", "outcome"),
)
RENDER_DURATION = Histogram(
    "ai_video_editor_worker_render_duration_seconds",
    "Worker render job duration by variant.",
    ("variant",),
)
CALLBACKS = Counter(
    "ai_video_editor_worker_callbacks",
    "Worker callback attempts by operation and outcome.",
    ("operation", "outcome"),
)


def record_render_job(*, variant: str, outcome: str, elapsed_seconds: float) -> None:
    RENDER_JOBS.labels(variant=normalized_variant(variant), outcome=outcome).inc()
    RENDER_DURATION.labels(variant=normalized_variant(variant)).observe(elapsed_seconds)


def record_callback(*, operation: str, outcome: str) -> None:
    CALLBACKS.labels(operation=operation, outcome=outcome).inc()


def start_worker_metrics_server() -> None:
    if settings.metrics_port <= 0:
        return
    registry = REGISTRY
    multiprocess_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")
    if multiprocess_dir:
        path = Path(multiprocess_dir)
        path.mkdir(parents=True, exist_ok=True)
        for shard in path.glob("*.db"):
            shard.unlink()
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    start_http_server(settings.metrics_port, registry=registry)


def normalized_variant(variant: str) -> str:
    return variant if variant in {"youtube_16x9", "shorts_9x16"} else "unknown"
