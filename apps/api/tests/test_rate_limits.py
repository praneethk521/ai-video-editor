from __future__ import annotations

from redis.exceptions import RedisError

from app.core.config import settings
from app.models.entities import ProjectUsageCounter
from app.services.quotas import ANALYSIS_REQUESTS, PROVIDER_COST_CENTS
from app.services import rate_limits
from app.services.rate_limits import reset_rate_limits


class FakeRedisRateLimitBackend:
    def __init__(self, *, unavailable: bool = False):
        self.counts: dict[str, int] = {}
        self.unavailable = unavailable

    def eval(self, script: str, key_count: int, key: str, window_seconds: int):
        if self.unavailable:
            raise RedisError("redis unavailable")
        assert "INCR" in script
        assert key_count == 1
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], window_seconds]


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


def test_redis_rate_limit_backend_shares_atomic_window(client, auth_headers, monkeypatch):
    reset_rate_limits()
    fake_redis = FakeRedisRateLimitBackend()
    monkeypatch.setattr(settings, "rate_limit_backend", "redis")
    monkeypatch.setattr(settings, "expensive_workflow_rate_limit_per_minute", 1)
    monkeypatch.setattr(rate_limits, "_redis_client", lambda redis_url: fake_redis)
    project = client.post("/projects", json={"name": "Redis rate limit"}, headers=auth_headers).json()

    first = client.post(f"/projects/{project['id']}/sync-drive", headers=auth_headers)
    second = client.post(f"/projects/{project['id']}/sync-drive", headers=auth_headers)

    assert first.status_code == 422
    assert second.status_code == 429
    assert len(fake_redis.counts) == 1
    assert next(iter(fake_redis.counts.values())) == 2


def test_redis_rate_limit_backend_fails_closed(client, auth_headers, monkeypatch):
    reset_rate_limits()
    fake_redis = FakeRedisRateLimitBackend(unavailable=True)
    monkeypatch.setattr(settings, "rate_limit_backend", "redis")
    monkeypatch.setattr(rate_limits, "_redis_client", lambda redis_url: fake_redis)
    project = client.post("/projects", json={"name": "Unavailable limiter"}, headers=auth_headers).json()

    response = client.post(f"/projects/{project['id']}/sync-drive", headers=auth_headers)

    assert response.status_code == 503
    assert response.json()["detail"] == "rate limit backend unavailable"


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


def test_project_usage_summary_tracks_estimated_provider_cost(client, auth_headers, monkeypatch):
    reset_rate_limits()
    monkeypatch.setattr(settings, "analysis_provider_estimated_cost_cents_per_request", 25)
    monkeypatch.setattr(settings, "provider_cost_cents_per_project_per_day", 50)
    project = client.post("/projects", json={"name": "Cost tracked project"}, headers=auth_headers).json()

    analyzed = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)
    usage = client.get(f"/projects/{project['id']}/usage", headers=auth_headers)

    assert analyzed.status_code == 422
    assert usage.status_code == 200
    metrics = {row["metric"]: row for row in usage.json()["metrics"]}
    assert metrics[ANALYSIS_REQUESTS]["used"] == 1
    assert metrics[PROVIDER_COST_CENTS]["used"] == 25
    assert metrics[PROVIDER_COST_CENTS]["remaining"] == 25
    assert usage.json()["active_delivered_storage_bytes"] == 0
