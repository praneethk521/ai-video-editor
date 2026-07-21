from __future__ import annotations

from app.core.config import settings
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
