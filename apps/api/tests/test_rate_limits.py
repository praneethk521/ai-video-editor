from __future__ import annotations

from app.core.config import settings
from app.models.entities import ProjectUsageCounter
from app.services.quotas import ANALYSIS_REQUESTS
from app.services.rate_limits import reset_rate_limits


def test_expensive_project_workflow_rate_limit_returns_429(client, auth_headers, monkeypatch):
    reset_rate_limits()
    monkeypatch.setattr(settings, "expensive_workflow_rate_limit_per_minute", 1)
    project = client.post("/projects", json={"name": "Rate limited project"}, headers=auth_headers).json()

    try:
        first = client.post(f"/projects/{project['id']}/sync-drive", headers=auth_headers)
        second = client.post(f"/projects/{project['id']}/sync-drive", headers=auth_headers)
    finally:
        reset_rate_limits()

    assert first.status_code == 422
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0


def test_project_analysis_quota_returns_429(client, auth_headers, db_session, monkeypatch):
    reset_rate_limits()
    monkeypatch.setattr(settings, "analysis_requests_per_project_per_day", 1)
    project = client.post("/projects", json={"name": "Quota limited project"}, headers=auth_headers).json()

    first = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)
    second = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)

    counter = (
        db_session.query(ProjectUsageCounter)
        .filter(ProjectUsageCounter.project_id == project["id"], ProjectUsageCounter.metric == ANALYSIS_REQUESTS)
        .one()
    )
    assert first.status_code == 422
    assert second.status_code == 429
    assert second.json()["detail"]["metric"] == ANALYSIS_REQUESTS
    assert counter.used == 1
