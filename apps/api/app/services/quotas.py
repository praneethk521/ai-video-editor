from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import OutputVideo, ProjectUsageCounter

ANALYSIS_REQUESTS = "analysis_requests"
RENDER_JOBS = "render_jobs"
DELIVERED_STORAGE_BYTES = "delivered_storage_bytes"
DELIVERY_ATTEMPTS = "delivery_attempts"
PROVIDER_COST_CENTS = "provider_cost_cents"
DAY_SECONDS = 24 * 60 * 60

METRIC_DETAILS = {
    ANALYSIS_REQUESTS: ("Analysis requests", "requests"),
    RENDER_JOBS: ("Render jobs", "jobs"),
    DELIVERED_STORAGE_BYTES: ("Delivered storage added", "bytes"),
    DELIVERY_ATTEMPTS: ("Delivery attempts", "attempts"),
    PROVIDER_COST_CENTS: ("Estimated provider cost", "cents"),
}


def consume_project_quota(
    db: Session,
    *,
    project_id: str,
    metric: str,
    amount: int = 1,
    limit: int | None = None,
    window_seconds: int = DAY_SECONDS,
) -> ProjectUsageCounter | None:
    return record_project_usage(
        db,
        project_id=project_id,
        metric=metric,
        amount=amount,
        limit=limit,
        window_seconds=window_seconds,
        enforce_limit=settings.quota_enforcement_enabled,
    )


def record_project_usage(
    db: Session,
    *,
    project_id: str,
    metric: str,
    amount: int = 1,
    limit: int | None = None,
    window_seconds: int = DAY_SECONDS,
    enforce_limit: bool = False,
) -> ProjectUsageCounter | None:
    if amount <= 0:
        return None
    metric_limit = limit if limit is not None else limit_for_metric(metric)
    if metric_limit <= 0:
        return None

    window_start = current_window_start(window_seconds=window_seconds)
    counter = (
        db.query(ProjectUsageCounter)
        .filter(
            ProjectUsageCounter.project_id == project_id,
            ProjectUsageCounter.metric == metric,
            ProjectUsageCounter.window_start == window_start,
        )
        .one_or_none()
    )
    if counter is None:
        counter = ProjectUsageCounter(
            project_id=project_id,
            metric=metric,
            window_start=window_start,
            window_seconds=window_seconds,
            used=0,
            limit=metric_limit,
        )
        db.add(counter)
    counter.limit = metric_limit
    if enforce_limit and counter.used + amount > counter.limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "project quota exceeded",
                "metric": metric,
                "limit": counter.limit,
                "used": counter.used,
            },
        )
    counter.used += amount
    db.flush()
    return counter


def ensure_project_quota_available(
    db: Session,
    *,
    project_id: str,
    metric: str,
    amount: int = 1,
    limit: int | None = None,
    window_seconds: int = DAY_SECONDS,
) -> None:
    if not settings.quota_enforcement_enabled or amount <= 0:
        return
    metric_limit = limit if limit is not None else limit_for_metric(metric)
    if metric_limit <= 0:
        return
    window_start = current_window_start(window_seconds=window_seconds)
    counter = (
        db.query(ProjectUsageCounter)
        .filter(
            ProjectUsageCounter.project_id == project_id,
            ProjectUsageCounter.metric == metric,
            ProjectUsageCounter.window_start == window_start,
        )
        .one_or_none()
    )
    used = counter.used if counter is not None else 0
    if used + amount > metric_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "project quota exceeded",
                "metric": metric,
                "limit": metric_limit,
                "used": used,
            },
        )


def project_usage_summary(db: Session, *, project_id: str) -> dict:
    window_start = current_window_start(window_seconds=DAY_SECONDS)
    window_end = window_start + timedelta(seconds=DAY_SECONDS)
    counters = {
        counter.metric: counter
        for counter in db.query(ProjectUsageCounter)
        .filter(
            ProjectUsageCounter.project_id == project_id,
            ProjectUsageCounter.window_start == window_start,
        )
        .all()
    }
    metrics = []
    for metric, (label, unit) in METRIC_DETAILS.items():
        configured_limit = limit_for_metric(metric)
        counter = counters.get(metric)
        used = counter.used if counter is not None else 0
        metric_limit = counter.limit if counter is not None else configured_limit
        metrics.append(
            {
                "metric": metric,
                "label": label,
                "unit": unit,
                "used": used,
                "limit": metric_limit,
                "remaining": max(metric_limit - used, 0),
            }
        )

    delivered_outputs = (
        db.query(OutputVideo)
        .filter(OutputVideo.project_id == project_id, OutputVideo.delivery_status == "delivered")
        .all()
    )
    retained_outputs = [
        output
        for output in delivered_outputs
        if ((output.delivery_json or {}).get("delivered_artifact_cleanup") or {}).get("status") != "deleted"
    ]
    return {
        "project_id": project_id,
        "window_start": window_start,
        "window_end": window_end,
        "metrics": metrics,
        "active_delivered_storage_bytes": sum(output.file_size_bytes for output in retained_outputs),
        "active_delivered_output_count": len(retained_outputs),
    }


def limit_for_metric(metric: str) -> int:
    if metric == ANALYSIS_REQUESTS:
        return settings.analysis_requests_per_project_per_day
    if metric == RENDER_JOBS:
        return settings.render_jobs_per_project_per_day
    if metric == DELIVERED_STORAGE_BYTES:
        return settings.delivered_storage_bytes_per_project_per_day
    if metric == DELIVERY_ATTEMPTS:
        return settings.delivery_attempts_per_project_per_day
    if metric == PROVIDER_COST_CENTS:
        return settings.provider_cost_cents_per_project_per_day
    return 0


def current_window_start(*, window_seconds: int) -> datetime:
    now = datetime.now(timezone.utc)
    if window_seconds == DAY_SECONDS:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = int((now - epoch).total_seconds())
    return epoch + timedelta(seconds=elapsed - (elapsed % window_seconds))
