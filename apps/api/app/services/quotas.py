from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ProjectUsageCounter

ANALYSIS_REQUESTS = "analysis_requests"
RENDER_JOBS = "render_jobs"
DAY_SECONDS = 24 * 60 * 60


def consume_project_quota(
    db: Session,
    *,
    project_id: str,
    metric: str,
    amount: int = 1,
    limit: int | None = None,
    window_seconds: int = DAY_SECONDS,
) -> ProjectUsageCounter | None:
    if not settings.quota_enforcement_enabled:
        return None
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
    if counter.used + amount > counter.limit:
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


def limit_for_metric(metric: str) -> int:
    if metric == ANALYSIS_REQUESTS:
        return settings.analysis_requests_per_project_per_day
    if metric == RENDER_JOBS:
        return settings.render_jobs_per_project_per_day
    return 0


def current_window_start(*, window_seconds: int) -> datetime:
    now = datetime.now(timezone.utc)
    if window_seconds == DAY_SECONDS:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    elapsed = int((now - epoch).total_seconds())
    return epoch + timedelta(seconds=elapsed - (elapsed % window_seconds))
