from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import OutputVideo, ProjectUsageCounter, new_id, utcnow

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
    if enforce_limit and amount > metric_limit:
        raise_quota_exceeded(metric=metric, metric_limit=metric_limit, used=0)
    dialect = db.get_bind().dialect.name
    if dialect in {"postgresql", "sqlite"}:
        return record_project_usage_atomic(
            db,
            project_id=project_id,
            metric=metric,
            amount=amount,
            metric_limit=metric_limit,
            window_start=window_start,
            window_seconds=window_seconds,
            enforce_limit=enforce_limit,
            dialect=dialect,
        )
    return record_project_usage_locked(
        db,
        project_id=project_id,
        metric=metric,
        amount=amount,
        metric_limit=metric_limit,
        window_start=window_start,
        window_seconds=window_seconds,
        enforce_limit=enforce_limit,
    )


def record_project_usage_atomic(
    db: Session,
    *,
    project_id: str,
    metric: str,
    amount: int,
    metric_limit: int,
    window_start: datetime,
    window_seconds: int,
    enforce_limit: bool,
    dialect: str,
) -> ProjectUsageCounter:
    table = ProjectUsageCounter.__table__
    insert_factory = postgresql_insert if dialect == "postgresql" else sqlite_insert
    now = utcnow()
    insert_statement = insert_factory(table).values(
        id=new_id(),
        project_id=project_id,
        metric=metric,
        window_start=window_start,
        window_seconds=window_seconds,
        used=amount,
        limit=metric_limit,
        created_at=now,
        updated_at=now,
    )
    update_where = table.c.used + amount <= metric_limit if enforce_limit else None
    upsert = insert_statement.on_conflict_do_update(
        index_elements=[table.c.project_id, table.c.metric, table.c.window_start],
        set_={
            "window_seconds": window_seconds,
            "used": table.c.used + amount,
            "limit": metric_limit,
            "updated_at": now,
        },
        where=update_where,
    ).returning(table.c.id)
    row = db.execute(upsert).one_or_none()
    if row is None:
        used = current_project_usage(db, project_id=project_id, metric=metric, window_start=window_start)
        raise_quota_exceeded(metric=metric, metric_limit=metric_limit, used=used)
    counter = db.get(ProjectUsageCounter, row.id, populate_existing=True)
    if counter is None:
        raise RuntimeError("project usage counter upsert did not return a persisted row")
    return counter


def record_project_usage_locked(
    db: Session,
    *,
    project_id: str,
    metric: str,
    amount: int,
    metric_limit: int,
    window_start: datetime,
    window_seconds: int,
    enforce_limit: bool,
) -> ProjectUsageCounter:
    counter = (
        db.query(ProjectUsageCounter)
        .filter(
            ProjectUsageCounter.project_id == project_id,
            ProjectUsageCounter.metric == metric,
            ProjectUsageCounter.window_start == window_start,
        )
        .with_for_update()
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
        raise_quota_exceeded(metric=metric, metric_limit=counter.limit, used=counter.used)
    counter.used += amount
    db.flush()
    return counter


def current_project_usage(db: Session, *, project_id: str, metric: str, window_start: datetime) -> int:
    counter = (
        db.query(ProjectUsageCounter)
        .filter(
            ProjectUsageCounter.project_id == project_id,
            ProjectUsageCounter.metric == metric,
            ProjectUsageCounter.window_start == window_start,
        )
        .one_or_none()
    )
    return counter.used if counter is not None else 0


def raise_quota_exceeded(*, metric: str, metric_limit: int, used: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "message": "project quota exceeded",
            "metric": metric,
            "limit": metric_limit,
            "used": used,
        },
    )


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
