from __future__ import annotations

from app.core.security import hash_service_token
from app.models.entities import ServiceToken


def test_metrics_endpoint_requires_authentication_and_exports_runtime_metrics(client, auth_headers):
    health = client.get("/healthz")
    unauthorized = client.get("/metrics")
    metrics = client.get("/metrics", headers=auth_headers)

    assert health.status_code == 200
    assert unauthorized.status_code == 401
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "ai_video_editor_api_http_requests_total" in metrics.text
    assert 'route="/healthz"' in metrics.text
    assert "ai_video_editor_render_queue_depth" in metrics.text
    assert 'dependency="render_queue"' in metrics.text


def test_metrics_export_quota_and_workflow_decisions(client, auth_headers):
    project = client.post("/projects", json={"name": "Observed project"}, headers=auth_headers).json()
    analyzed = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)
    metrics = client.get("/metrics", headers=auth_headers)

    assert analyzed.status_code == 422
    assert metrics.status_code == 200
    assert "ai_video_editor_quota_decisions_total" in metrics.text
    assert 'metric="analysis_requests"' in metrics.text
    assert "ai_video_editor_workflow_events_total" in metrics.text
    assert 'workflow="analysis"' in metrics.text


def test_metrics_endpoint_rejects_project_scoped_service_tokens(client, auth_headers, db_session):
    project = client.post("/projects", json={"name": "Scoped metrics project"}, headers=auth_headers).json()
    token_value = "project-metrics-token"
    db_session.add(
        ServiceToken(
            name="Project metrics",
            token_hash=hash_service_token(token_value),
            role="worker",
            scope="metrics",
            project_id=project["id"],
        )
    )
    db_session.commit()

    response = client.get("/metrics", headers={"Authorization": f"Bearer {token_value}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "global service token required"
