from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import MediaAsset, OAuthConnection, Project, ProjectStatus
from app.services.malware import ScanResult
from app.services.media import decrypt_token_payload


def test_project_lifecycle_keeps_private_media(client, auth_headers):
    created = client.post("/projects", json={"name": "Launch video"}, headers=auth_headers)
    assert created.status_code == 201
    project_id = created.json()["id"]

    connected = client.post(
        f"/projects/{project_id}/connect-drive",
        json={"folder_url": "https://drive.google.com/drive/folders/private-folder-id"},
        headers=auth_headers,
    )
    assert connected.status_code == 200
    assert connected.json()["scopes"] == "https://www.googleapis.com/auth/drive.readonly"
    assert connected.json()["authorization_url"] is not None

    ingested = client.post(
        f"/projects/{project_id}/ingest",
        json={
            "assets": [
                {
                    "filename": "hero clip.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 123456,
                    "duration_seconds": 12,
                    "orientation": "landscape",
                    "private_locator": "drive://private-folder-id/hero-clip",
                }
            ]
        },
        headers=auth_headers,
    )
    assert ingested.status_code == 200
    assert len(ingested.json()["accepted_asset_ids"]) == 1
    media_asset_id = ingested.json()["accepted_asset_ids"][0]

    blocked_analysis = client.post(f"/projects/{project_id}/analyze", headers=auth_headers)
    assert blocked_analysis.status_code == 422

    scan = client.post(
        f"/internal/media-assets/{media_asset_id}/malware-scan",
        json={"status": "clean", "scanner": "unit-test", "details": {"signature_db": "test"}},
        headers=auth_headers,
    )
    assert scan.status_code == 204

    analyzed = client.post(f"/projects/{project_id}/analyze", headers=auth_headers)
    assert analyzed.status_code == 200
    assert len(analyzed.json()["timeline_plan_ids"]) == 2

    analysis = client.get(f"/projects/{project_id}/analysis", headers=auth_headers)
    assert analysis.status_code == 200
    assert len(analysis.json()["results"]) == 1
    analysis_result = analysis.json()["results"][0]
    assert analysis_result["provider"] == "deterministic-local-metadata-v1"
    assert analysis_result["result"]["privacy"]["media_bytes_used"] is False
    assert analysis_result["result"]["summary"]["scene_count"] == 2
    assert analysis_result["result"]["asset_features"][0]["highlight_score"] > 0.5

    plans = client.get(f"/projects/{project_id}/plans", headers=auth_headers)
    assert plans.status_code == 200
    assert {plan["status"] for plan in plans.json()["plans"]} == {"draft"}
    assert "provider_pending" not in plans.json()["plans"][0]["plan"]["strategy"]["hook"]
    assert plans.json()["plans"][0]["plan"]["tracks"][0]["clips"][0]["caption"] != "Auto-caption placeholder"

    blocked_render = client.post(
        f"/projects/{project_id}/render",
        json={"variants": ["youtube_16x9", "shorts_9x16"]},
        headers=auth_headers,
    )
    assert blocked_render.status_code == 422

    for plan_id in analyzed.json()["timeline_plan_ids"]:
        approved = client.post(
            f"/projects/{project_id}/plans/{plan_id}/approve",
            json={"notes": "Looks good for first render."},
            headers=auth_headers,
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

    rendered = client.post(f"/projects/{project_id}/render", json={"variants": ["youtube_16x9", "shorts_9x16"]}, headers=auth_headers)
    assert rendered.status_code == 200
    assert len(rendered.json()["render_job_ids"]) == 2

    status = client.get(f"/projects/{project_id}/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["status"] == "rendering"
    assert status.json()["media_count"] == 1

    for job in status.json()["render_jobs"]:
        running = client.post(f"/internal/render-jobs/{job['id']}/running", headers=auth_headers)
        assert running.status_code == 204
        width, height = (1920, 1080) if job["variant"] == "youtube_16x9" else (1080, 1920)
        completed = client.post(
            f"/internal/render-jobs/{job['id']}/complete",
            json={
                "variant": job["variant"],
                "private_locator": f"file://private/{project_id}/{job['variant']}.mp4",
                "width": width,
                "height": height,
                "duration_seconds": 12,
                "file_size_bytes": 2048,
                "upload_package": {"manual_upload_only": True},
                "validation": {"status": "passed", "checks": {"ffprobe": True}},
            },
            headers=auth_headers,
        )
        assert completed.status_code == 204

    ready = client.get(f"/projects/{project_id}/status", headers=auth_headers)
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert {job["status"] for job in ready.json()["render_jobs"]} == {"succeeded"}

    outputs = client.get(f"/projects/{project_id}/outputs", headers=auth_headers)
    assert outputs.status_code == 200
    assert len(outputs.json()["outputs"]) == 2
    assert all(output["upload_package"]["manual_upload_only"] is True for output in outputs.json()["outputs"])
    assert {output["validation"]["status"] for output in outputs.json()["outputs"]} == {"passed"}
    assert {output["delivery"]["status"] for output in outputs.json()["outputs"]} == {"private_staging"}

    first_output = outputs.json()["outputs"][0]
    public_delivery = client.post(
        f"/internal/output-videos/{first_output['id']}/delivery",
        json={"target": "drive", "status": "delivered", "delivered_locator": "https://example.com/output.mp4", "details": {}},
        headers=auth_headers,
    )
    assert public_delivery.status_code == 422

    delivered = client.post(
        f"/internal/output-videos/{first_output['id']}/delivery",
        json={
            "target": "drive",
            "status": "delivered",
            "delivered_locator": f"drive://private-output-folder/{first_output['variant']}.mp4",
            "details": {"provider": "unit-test"},
        },
        headers=auth_headers,
    )
    assert delivered.status_code == 204

    delivered_outputs = client.get(f"/projects/{project_id}/outputs", headers=auth_headers)
    delivered_output = next(output for output in delivered_outputs.json()["outputs"] if output["id"] == first_output["id"])
    assert delivered_output["delivery"]["status"] == "delivered"
    assert delivered_output["delivery"]["delivered_locator"].startswith("drive://private-output-folder/")


def test_s3_output_delivery_uploads_private_staged_file(client, auth_headers, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "output_delivery_local_root", str(tmp_path))
    monkeypatch.setattr(settings, "s3_bucket", "private-video-bucket")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_prefix", "renders")
    project = client.post("/projects", json={"name": "S3 Delivery"}, headers=auth_headers).json()
    output = create_completed_output(client, auth_headers, project["id"], tmp_path)
    uploaded = {}

    class FakeS3Client:
        def put_object(self, **kwargs):
            uploaded.update(kwargs)
            uploaded["Body"] = kwargs["Body"].read()

    monkeypatch.setattr("app.services.output_delivery._s3_client", lambda: FakeS3Client())

    delivered = client.post(
        f"/internal/output-videos/{output['id']}/deliver",
        json={"target": "s3"},
        headers=auth_headers,
    )
    assert delivered.status_code == 204
    assert uploaded["Bucket"] == "private-video-bucket"
    assert uploaded["Key"].startswith(f"renders/{project['id']}/")
    assert uploaded["Body"] == b"private rendered bytes"
    assert uploaded["ServerSideEncryption"] == "AES256"
    s3_tags = parse_qs(uploaded["Tagging"])
    assert s3_tags["privacy"] == ["private"]
    assert s3_tags["retention_policy"] == ["manual_upload_private_output"]
    assert s3_tags["retention_days"] == ["30"]

    outputs = client.get(f"/projects/{project['id']}/outputs", headers=auth_headers)
    delivered_output = outputs.json()["outputs"][0]
    assert delivered_output["delivery"]["status"] == "delivered"
    assert delivered_output["delivery"]["delivered_locator"].startswith("s3://private/private-video-bucket/renders/")
    assert delivered_output["delivery"]["details"]["details"]["retention"]["privacy"] == "private"


def test_drive_output_delivery_uploads_with_connected_oauth(client, auth_headers, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "output_delivery_local_root", str(tmp_path))
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(settings, "google_drive_output_folder_id", "private-output-folder")

    class FakeTokenResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "drive-upload-token", "refresh_token": "refresh-token", "expires_in": 3600}

    monkeypatch.setattr("app.services.media.httpx.post", lambda url, data, timeout: FakeTokenResponse())
    project = client.post("/projects", json={"name": "Drive Delivery"}, headers=auth_headers).json()
    connected = client.post(
        f"/projects/{project['id']}/connect-drive",
        json={"folder_url": "https://drive.google.com/drive/folders/source-folder"},
        headers=auth_headers,
    )
    state = parse_qs(urlparse(connected.json()["authorization_url"]).query)["state"][0]
    callback = client.get(f"/projects/{project['id']}/connect-drive/callback", params={"code": "oauth-code", "state": state})
    assert callback.status_code == 200
    output = create_completed_output(client, auth_headers, project["id"], tmp_path)
    uploaded = {}

    class FakeUploadResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "uploaded-drive-file"}

    def fake_upload(url, headers, content, timeout):
        uploaded.update({"url": url, "headers": headers, "content": content, "timeout": timeout})
        return FakeUploadResponse()

    monkeypatch.setattr("app.services.output_delivery.httpx.post", fake_upload)

    delivered = client.post(
        f"/internal/output-videos/{output['id']}/deliver",
        json={"target": "drive"},
        headers=auth_headers,
    )
    assert delivered.status_code == 204
    assert uploaded["url"] == settings.google_drive_upload_url
    assert uploaded["headers"]["Authorization"] == "Bearer drive-upload-token"
    assert b"private-output-folder" in uploaded["content"]
    assert b"appProperties" in uploaded["content"]
    assert b"manual_upload_private_output" in uploaded["content"]
    assert b"private rendered bytes" in uploaded["content"]

    outputs = client.get(f"/projects/{project['id']}/outputs", headers=auth_headers)
    delivered_output = outputs.json()["outputs"][0]
    assert delivered_output["delivery"]["status"] == "delivered"
    assert delivered_output["delivery"]["delivered_locator"] == "drive://private-output-folder/uploaded-drive-file"


def test_render_completion_can_auto_deliver_to_local_private(client, auth_headers, monkeypatch, tmp_path: Path):
    staging_root = tmp_path / "staging"
    delivered_root = tmp_path / "delivered"
    monkeypatch.setattr(settings, "auto_deliver_outputs", True)
    monkeypatch.setattr(settings, "output_delivery_local_root", str(staging_root))
    monkeypatch.setattr(settings, "local_private_delivery_root", str(delivered_root))
    project = client.post("/projects", json={"name": "Auto Delivery"}, headers=auth_headers).json()

    output = create_completed_output(client, auth_headers, project["id"], staging_root, delivery_target="local_private")

    outputs = client.get(f"/projects/{project['id']}/outputs", headers=auth_headers)
    delivered_output = next(row for row in outputs.json()["outputs"] if row["id"] == output["id"])
    assert delivered_output["delivery"]["status"] == "delivered"
    assert delivered_output["delivery"]["target"] == "local_private"
    assert delivered_output["delivery"]["delivered_locator"].startswith("file://private/delivered/")
    assert any(delivered_root.rglob("*.mp4"))


def test_output_delivery_failure_is_recorded_and_retryable(client, auth_headers, monkeypatch, tmp_path: Path):
    staging_root = tmp_path / "staging"
    delivered_root = tmp_path / "delivered"
    monkeypatch.setattr(settings, "output_delivery_local_root", str(staging_root))
    monkeypatch.setattr(settings, "local_private_delivery_root", str(delivered_root))
    project = client.post("/projects", json={"name": "Retry Delivery"}, headers=auth_headers).json()
    output = create_completed_output(client, auth_headers, project["id"], staging_root, delivery_target="local_private")
    staged_path = staging_root / project["id"] / "youtube_16x9.mp4"
    staged_path.unlink()

    failed = client.post(
        f"/internal/output-videos/{output['id']}/deliver",
        json={"target": "local_private"},
        headers=auth_headers,
    )
    assert failed.status_code == 422

    failed_outputs = client.get(f"/projects/{project['id']}/outputs", headers=auth_headers)
    failed_output = failed_outputs.json()["outputs"][0]
    assert failed_output["delivery"]["status"] == "failed"
    assert failed_output["delivery"]["details"]["details"]["phase"] == "manual_delivery"
    assert "staged output file is missing" in failed_output["delivery"]["details"]["details"]["error"]

    staged_path.write_bytes(b"private rendered bytes")
    retried = client.post(
        f"/internal/output-videos/{output['id']}/deliver",
        json={"target": "local_private"},
        headers=auth_headers,
    )
    assert retried.status_code == 204
    retried_outputs = client.get(f"/projects/{project['id']}/outputs", headers=auth_headers)
    retried_output = retried_outputs.json()["outputs"][0]
    assert retried_output["delivery"]["status"] == "delivered"


def test_local_private_smoke_workflow_project_to_delivery(client, auth_headers, monkeypatch, tmp_path: Path):
    staging_root = tmp_path / "staging"
    delivered_root = tmp_path / "delivered"
    monkeypatch.setattr(settings, "output_delivery_local_root", str(staging_root))
    monkeypatch.setattr(settings, "local_private_delivery_root", str(delivered_root))
    monkeypatch.setattr(settings, "cleanup_staged_outputs_after_delivery", True)

    project = client.post("/projects", json={"name": "Local smoke edit"}, headers=auth_headers).json()
    project_id = project["id"]
    ingested = client.post(
        f"/projects/{project_id}/ingest",
        json={
            "assets": [
                {
                    "filename": "hero clip.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 123456,
                    "duration_seconds": 12,
                    "orientation": "landscape",
                    "private_locator": "drive://private-smoke-folder/hero-clip",
                }
            ]
        },
        headers=auth_headers,
    )
    assert ingested.status_code == 200
    media_asset_id = ingested.json()["accepted_asset_ids"][0]

    scan = client.post(
        f"/internal/media-assets/{media_asset_id}/malware-scan",
        json={"status": "clean", "scanner": "local-smoke", "details": {"mode": "synthetic"}},
        headers=auth_headers,
    )
    assert scan.status_code == 204

    analyzed = client.post(f"/projects/{project_id}/analyze", headers=auth_headers)
    assert analyzed.status_code == 200
    assert len(analyzed.json()["timeline_plan_ids"]) == 2

    for plan_id in analyzed.json()["timeline_plan_ids"]:
        approved = client.post(
            f"/projects/{project_id}/plans/{plan_id}/approve",
            json={"notes": "Approved for local smoke test."},
            headers=auth_headers,
        )
        assert approved.status_code == 200

    rendered = client.post(
        f"/projects/{project_id}/render",
        json={"variants": ["youtube_16x9", "shorts_9x16"]},
        headers=auth_headers,
    )
    assert rendered.status_code == 200
    assert len(rendered.json()["render_job_ids"]) == 2

    status_response = client.get(f"/projects/{project_id}/status", headers=auth_headers)
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "rendering"
    assert {job["variant"] for job in status_response.json()["render_jobs"]} == {"youtube_16x9", "shorts_9x16"}

    for job in status_response.json()["render_jobs"]:
        staged_path = staging_root / project_id / f"{job['variant']}.mp4"
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(b"private rendered bytes")

        running = client.post(f"/internal/render-jobs/{job['id']}/running", headers=auth_headers)
        assert running.status_code == 204

        width, height = (1920, 1080) if job["variant"] == "youtube_16x9" else (1080, 1920)
        completed = client.post(
            f"/internal/render-jobs/{job['id']}/complete",
            json={
                "variant": job["variant"],
                "private_locator": f"file://private/{project_id}/{job['variant']}.mp4",
                "width": width,
                "height": height,
                "duration_seconds": 12,
                "file_size_bytes": staged_path.stat().st_size,
                "upload_package": {
                    "manual_upload_only": True,
                    "delivery_target": "local_private",
                    "delivery_status": "private_staging",
                },
                "validation": {"status": "passed", "checks": {"local_smoke": True}},
            },
            headers=auth_headers,
        )
        assert completed.status_code == 204

    ready = client.get(f"/projects/{project_id}/status", headers=auth_headers)
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    outputs = client.get(f"/projects/{project_id}/outputs", headers=auth_headers)
    assert outputs.status_code == 200
    assert len(outputs.json()["outputs"]) == 2
    assert {output["delivery"]["target"] for output in outputs.json()["outputs"]} == {"local_private"}
    assert {output["delivery"]["status"] for output in outputs.json()["outputs"]} == {"private_staging"}
    assert all(output["upload_package"]["manual_upload_only"] is True for output in outputs.json()["outputs"])
    assert {output["validation"]["status"] for output in outputs.json()["outputs"]} == {"passed"}

    for output in outputs.json()["outputs"]:
        delivered = client.post(
            f"/internal/output-videos/{output['id']}/deliver",
            json={"target": "local_private"},
            headers=auth_headers,
        )
        assert delivered.status_code == 204

    delivered_outputs = client.get(f"/projects/{project_id}/outputs", headers=auth_headers)
    assert delivered_outputs.status_code == 200
    assert {output["delivery"]["status"] for output in delivered_outputs.json()["outputs"]} == {"delivered"}
    assert all(
        output["delivery"]["delivered_locator"].startswith("file://private/delivered/")
        for output in delivered_outputs.json()["outputs"]
    )
    delivered_filenames = sorted(path.name for path in delivered_root.rglob("*.mp4"))
    assert len(delivered_filenames) == 2
    assert any(name.startswith("shorts_9x16-") for name in delivered_filenames)
    assert any(name.startswith("youtube_16x9-") for name in delivered_filenames)
    assert len(list(delivered_root.rglob("*.retention.json"))) == 2
    assert not any(staging_root.rglob("*.mp4"))
    assert all(
        output["delivery"]["details"]["staged_source_cleanup"]["status"] == "deleted"
        for output in delivered_outputs.json()["outputs"]
    )
    assert all(
        output["delivery"]["details"]["details"]["retention"]["retention_days"] == "30"
        for output in delivered_outputs.json()["outputs"]
    )

    retention_report = client.get(f"/projects/{project_id}/outputs/retention", headers=auth_headers)
    assert retention_report.status_code == 200
    retention_rows = retention_report.json()["outputs"]
    assert len(retention_rows) == 2
    assert {row["target"] for row in retention_rows} == {"local_private"}
    assert {row["status"] for row in retention_rows} == {"delivered"}
    assert all(row["has_retention_metadata"] is True for row in retention_rows)
    assert all(row["retention"]["privacy"] == "private" for row in retention_rows)
    assert all(row["cleanup_status"] == "deleted" for row in retention_rows)
    assert all(row["days_until_delete"] is not None and row["days_until_delete"] > 0 for row in retention_rows)
    assert {row["retention_due"] for row in retention_rows} == {False}


def test_rejects_public_media_urls_and_path_traversal(client, auth_headers):
    project = client.post("/projects", json={"name": "Secure ingest"}, headers=auth_headers).json()
    response = client.post(
        f"/projects/{project['id']}/ingest",
        json={
            "assets": [
                {
                    "filename": "../secret.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 123,
                    "private_locator": "https://example.com/secret.mp4",
                }
            ]
        },
        headers=auth_headers,
    )
    assert response.status_code == 422


def create_completed_output(client, auth_headers, project_id: str, local_root: Path, delivery_target: str = "drive") -> dict:
    ingested = client.post(
        f"/projects/{project_id}/ingest",
        json={
            "assets": [
                {
                    "filename": "clip.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 123,
                    "duration_seconds": 5,
                    "private_locator": "drive://private-folder-id/clip",
                }
            ]
        },
        headers=auth_headers,
    )
    media_asset_id = ingested.json()["accepted_asset_ids"][0]
    scan = client.post(
        f"/internal/media-assets/{media_asset_id}/malware-scan",
        json={"status": "clean", "scanner": "unit-test", "details": {}},
        headers=auth_headers,
    )
    assert scan.status_code == 204
    analyzed = client.post(f"/projects/{project_id}/analyze", headers=auth_headers)
    assert analyzed.status_code == 200
    for plan_id in analyzed.json()["timeline_plan_ids"]:
        approved = client.post(f"/projects/{project_id}/plans/{plan_id}/approve", json={"notes": None}, headers=auth_headers)
        assert approved.status_code == 200
    rendered = client.post(f"/projects/{project_id}/render", json={"variants": ["youtube_16x9"]}, headers=auth_headers)
    assert rendered.status_code == 200
    status_response = client.get(f"/projects/{project_id}/status", headers=auth_headers)
    job = status_response.json()["render_jobs"][0]
    staged_path = local_root / project_id / f"{job['variant']}.mp4"
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    staged_path.write_bytes(b"private rendered bytes")
    completed = client.post(
        f"/internal/render-jobs/{job['id']}/complete",
        json={
            "variant": job["variant"],
            "private_locator": f"file://private/{project_id}/{job['variant']}.mp4",
            "width": 1920,
            "height": 1080,
            "duration_seconds": 5,
            "file_size_bytes": staged_path.stat().st_size,
            "upload_package": {
                "manual_upload_only": True,
                "delivery_target": delivery_target,
                "delivery_status": "private_staging",
            },
            "validation": {"status": "passed", "checks": {"ffprobe": True}},
        },
        headers=auth_headers,
    )
    assert completed.status_code == 204
    outputs = client.get(f"/projects/{project_id}/outputs", headers=auth_headers)
    assert outputs.status_code == 200
    return outputs.json()["outputs"][0]


def test_requires_authentication(client):
    response = client.post("/projects", json={"name": "Nope"})
    assert response.status_code == 401


def test_analysis_provider_health_endpoint(client, auth_headers):
    response = client.get("/internal/analysis-provider/health", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["provider"] == "deterministic-local-metadata-v1"

    metrics = client.get("/internal/analysis-provider/metrics", headers=auth_headers)
    assert metrics.status_code == 200
    local_metrics = metrics.json()["providers"]["deterministic-local-metadata-v1"]
    assert local_metrics["health_checks"] >= 1
    assert local_metrics["last_status"] == "health_healthy"


def test_google_oauth_callback_encrypts_tokens(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")

    captured_token_request = {}

    class FakeTokenResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "access_token": "access-token-value",
                "refresh_token": "refresh-token-value",
                "expires_in": 3600,
                "scope": settings.google_drive_scopes,
                "token_type": "Bearer",
            }

    def fake_post(url, data, timeout):
        captured_token_request["url"] = url
        captured_token_request["data"] = data
        captured_token_request["timeout"] = timeout
        return FakeTokenResponse()

    monkeypatch.setattr("app.services.media.httpx.post", fake_post)

    project = client.post("/projects", json={"name": "Drive OAuth"}, headers=auth_headers).json()
    connected = client.post(
        f"/projects/{project['id']}/connect-drive",
        json={"folder_url": "https://drive.google.com/drive/folders/private-folder-id"},
        headers=auth_headers,
    )
    assert connected.status_code == 200
    authorization_url = connected.json()["authorization_url"]
    state = parse_qs(urlparse(authorization_url).query)["state"][0]

    callback = client.get(f"/projects/{project['id']}/connect-drive/callback", params={"code": "oauth-code", "state": state})
    assert callback.status_code == 200
    assert callback.json()["status"] == "connected"

    assert captured_token_request["url"] == settings.google_oauth_token_url
    assert captured_token_request["data"]["code"] == "oauth-code"
    assert captured_token_request["data"]["client_secret"] == "client-secret"

    with SessionLocal() as db:
        connection = db.get(OAuthConnection, connected.json()["connection_id"])
        assert connection is not None
        assert connection.status == "connected"
        assert connection.oauth_state_hash is None
        assert connection.selected_folder_id == "private-folder-id"
        assert connection.encrypted_token_json is not None
        assert "access-token-value" not in connection.encrypted_token_json
        token_payload = decrypt_token_payload(connection.encrypted_token_json)
        assert token_payload["access_token"] == "access-token-value"


def test_sync_drive_folder_ingests_private_media_and_skips_duplicates(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")

    class FakeTokenResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "drive-access-token", "refresh_token": "refresh-token", "expires_in": 3600}

    def fake_token_post(url, data, timeout):
        return FakeTokenResponse()

    drive_requests = []

    class FakeDriveResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_drive_get(url, headers, params, timeout):
        drive_requests.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if "pageToken" not in params:
            return FakeDriveResponse(
                {
                    "nextPageToken": "page-2",
                    "files": [
                        {
                            "id": "video-1",
                            "name": "hero clip.mp4",
                            "mimeType": "video/mp4",
                            "size": "123456",
                            "md5Checksum": "checksum-1",
                            "videoMediaMetadata": {"durationMillis": "12000", "width": 1920, "height": 1080},
                        },
                        {
                            "id": "video-duplicate",
                            "name": "hero duplicate.mp4",
                            "mimeType": "video/mp4",
                            "size": "123456",
                            "md5Checksum": "checksum-1",
                            "videoMediaMetadata": {"durationMillis": "12000", "width": 1920, "height": 1080},
                        },
                    ],
                }
            )
        return FakeDriveResponse(
            {
                "files": [
                    {
                        "id": "image-1",
                        "name": "thumbnail.png",
                        "mimeType": "image/png",
                        "size": "2048",
                        "md5Checksum": "checksum-2",
                        "imageMediaMetadata": {"width": 1080, "height": 1920},
                    },
                    {
                        "id": "doc-1",
                        "name": "notes.txt",
                        "mimeType": "text/plain",
                        "size": "100",
                        "md5Checksum": "checksum-3",
                    },
                ]
            }
        )

    monkeypatch.setattr("app.services.media.httpx.post", fake_token_post)
    monkeypatch.setattr("app.services.media.httpx.get", fake_drive_get)

    project = client.post("/projects", json={"name": "Drive Sync"}, headers=auth_headers).json()
    connected = client.post(
        f"/projects/{project['id']}/connect-drive",
        json={"folder_url": "https://drive.google.com/drive/folders/private-folder-id"},
        headers=auth_headers,
    )
    state = parse_qs(urlparse(connected.json()["authorization_url"]).query)["state"][0]
    callback = client.get(f"/projects/{project['id']}/connect-drive/callback", params={"code": "oauth-code", "state": state})
    assert callback.status_code == 200

    synced = client.post(f"/projects/{project['id']}/sync-drive", headers=auth_headers)
    assert synced.status_code == 200
    assert synced.json()["discovered_count"] == 4
    assert len(synced.json()["accepted_asset_ids"]) == 2
    assert synced.json()["duplicate_count"] == 1
    assert synced.json()["skipped_count"] == 1
    assert len(drive_requests) == 2
    assert drive_requests[0]["headers"]["Authorization"] == "Bearer drive-access-token"
    assert drive_requests[0]["params"]["q"] == "'private-folder-id' in parents and trashed=false"

    status = client.get(f"/projects/{project['id']}/status", headers=auth_headers)
    assert status.json()["media_count"] == 2


def test_regenerate_and_reject_timeline_plan(client, auth_headers):
    project = client.post("/projects", json={"name": "Review Flow"}, headers=auth_headers).json()
    ingested = client.post(
        f"/projects/{project['id']}/ingest",
        json={
            "assets": [
                {
                    "filename": "clip.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 123,
                    "duration_seconds": 5,
                    "private_locator": "drive://private-folder-id/clip",
                }
            ]
        },
        headers=auth_headers,
    )
    media_asset_id = ingested.json()["accepted_asset_ids"][0]
    scan = client.post(
        f"/internal/media-assets/{media_asset_id}/malware-scan",
        json={"status": "clean", "scanner": "unit-test", "details": {}},
        headers=auth_headers,
    )
    assert scan.status_code == 204
    analyzed = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)
    assert analyzed.status_code == 200
    first_plan_id = analyzed.json()["timeline_plan_ids"][0]

    rejected = client.post(
        f"/projects/{project['id']}/plans/{first_plan_id}/reject",
        json={"notes": "Needs a faster hook."},
        headers=auth_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["review_notes"] == "Needs a faster hook."

    regenerated = client.post(
        f"/projects/{project['id']}/plans/regenerate",
        json={"variants": ["youtube_16x9"], "notes": "Needs a faster hook."},
        headers=auth_headers,
    )
    assert regenerated.status_code == 200
    assert len(regenerated.json()["timeline_plan_ids"]) == 1
    assert regenerated.json()["timeline_plan_ids"][0] != first_plan_id

    plans = client.get(f"/projects/{project['id']}/plans", headers=auth_headers)
    assert plans.status_code == 200
    assert len(plans.json()["plans"]) == 3


def test_external_http_analysis_provider_uses_sanitized_metadata(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "analysis_provider", "external_http")
    monkeypatch.setattr(settings, "analysis_provider_url", "https://analysis.internal/analyze")
    monkeypatch.setattr(settings, "analysis_provider_token", "provider-token")
    monkeypatch.setattr(settings, "analysis_provider_include_private_locator", False)
    monkeypatch.setattr(settings, "analysis_provider_retry_backoff_seconds", 0)
    before_metrics = client.get("/internal/analysis-provider/metrics", headers=auth_headers).json()["providers"].get(
        "external-http-analysis-v1", {}
    )
    captured = {}
    attempts = []

    class FakeAnalysisResponse:
        def raise_for_status(self):
            return None

        def json(self):
            asset_id = captured["json"]["assets"][0]["asset_id"]
            return {
                "provider": "unit-test-analysis-provider",
                "summary": {
                    "asset_count": 1,
                    "scene_count": 4,
                    "primary_orientation": "portrait",
                    "average_highlight_score": 0.91,
                    "subjects_detected": 1,
                    "audio_quality": "good",
                    "duplicate_clip_detection": "no_duplicates_found",
                },
                "asset_features": [
                    {
                        "asset_id": asset_id,
                        "mime_type": "video/mp4",
                        "duration_seconds": 9,
                        "orientation": "portrait",
                        "scene_count": 4,
                        "highlight_score": 0.91,
                        "tags": ["interview", "talking_head"],
                        "subject": {"presence": "likely_human", "confidence": 0.88, "framing": "face_subject"},
                        "audio": {"quality": "good", "score": 0.9, "recommended_lufs": -14},
                        "visual": {"quality": "usable", "blur_risk": "low", "motion": "unknown"},
                    }
                ],
            }

    def fake_post(url, headers, json, timeout):
        attempts.append(url)
        if len(attempts) == 1:
            raise httpx.ConnectError("temporary outage")
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeAnalysisResponse()

    monkeypatch.setattr("app.services.analysis_providers.httpx.post", fake_post)

    project = client.post("/projects", json={"name": "External Analysis"}, headers=auth_headers).json()
    ingested = client.post(
        f"/projects/{project['id']}/ingest",
        json={
            "assets": [
                {
                    "filename": "interview.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 900000,
                    "duration_seconds": 9,
                    "orientation": "portrait",
                    "private_locator": "drive://private-folder-id/interview",
                }
            ]
        },
        headers=auth_headers,
    )
    media_asset_id = ingested.json()["accepted_asset_ids"][0]
    scan = client.post(
        f"/internal/media-assets/{media_asset_id}/malware-scan",
        json={"status": "clean", "scanner": "unit-test", "details": {}},
        headers=auth_headers,
    )
    assert scan.status_code == 204

    analyzed = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)
    assert analyzed.status_code == 200

    assert captured["url"] == "https://analysis.internal/analyze"
    assert attempts == ["https://analysis.internal/analyze", "https://analysis.internal/analyze"]
    assert captured["headers"]["Authorization"] == "Bearer provider-token"
    assert captured["timeout"] == settings.analysis_provider_timeout_seconds
    assert "private_locator" not in captured["json"]["assets"][0]
    assert captured["json"]["assets"][0]["sanitized_filename"] == "interview.mp4"

    analysis = client.get(f"/projects/{project['id']}/analysis", headers=auth_headers)
    assert analysis.json()["results"][0]["provider"] == "unit-test-analysis-provider"
    assert analysis.json()["results"][0]["result"]["privacy"]["private_locator_included"] is False

    plans = client.get(f"/projects/{project['id']}/plans", headers=auth_headers)
    assert "talking head" in plans.json()["plans"][0]["plan"]["strategy"]["hook"]
    assert plans.json()["plans"][0]["plan"]["tracks"][0]["clips"][0]["effect"] in {"match_cut", "subject_push", "subtle_zoom"}

    after_metrics = client.get("/internal/analysis-provider/metrics", headers=auth_headers).json()["providers"][
        "external-http-analysis-v1"
    ]
    assert after_metrics["analyze_successes"] == before_metrics.get("analyze_successes", 0) + 1
    assert after_metrics["retry_attempts"] == before_metrics.get("retry_attempts", 0) + 1
    assert after_metrics["last_status"] == "success"
    assert after_metrics["last_duration_ms"] >= 0


def test_external_http_analysis_provider_circuit_breaker(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "analysis_provider", "external_http")
    monkeypatch.setattr(settings, "analysis_provider_url", "https://analysis.internal/analyze")
    monkeypatch.setattr(settings, "analysis_provider_max_attempts", 1)
    monkeypatch.setattr(settings, "analysis_provider_retry_backoff_seconds", 0)
    monkeypatch.setattr(settings, "analysis_provider_circuit_failure_threshold", 1)
    monkeypatch.setattr(settings, "analysis_provider_circuit_reset_seconds", 60)
    before_metrics = client.get("/internal/analysis-provider/metrics", headers=auth_headers).json()["providers"].get(
        "external-http-analysis-v1", {}
    )
    attempts = []

    def fake_post(url, headers, json, timeout):
        attempts.append(url)
        raise httpx.ConnectError("provider unavailable")

    monkeypatch.setattr("app.services.analysis_providers.httpx.post", fake_post)

    project = client.post("/projects", json={"name": "Circuit Breaker"}, headers=auth_headers).json()
    ingested = client.post(
        f"/projects/{project['id']}/ingest",
        json={
            "assets": [
                {
                    "filename": "clip.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 900000,
                    "duration_seconds": 9,
                    "orientation": "landscape",
                    "private_locator": "drive://private-folder-id/clip",
                }
            ]
        },
        headers=auth_headers,
    )
    media_asset_id = ingested.json()["accepted_asset_ids"][0]
    scan = client.post(
        f"/internal/media-assets/{media_asset_id}/malware-scan",
        json={"status": "clean", "scanner": "unit-test", "details": {}},
        headers=auth_headers,
    )
    assert scan.status_code == 204

    first = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)
    assert first.status_code == 422
    assert first.json()["detail"]["message"] == "analysis provider unavailable"
    assert attempts == ["https://analysis.internal/analyze"]

    second = client.post(f"/projects/{project['id']}/analyze", headers=auth_headers)
    assert second.status_code == 422
    assert second.json()["detail"]["message"] == "analysis provider circuit is open"
    assert second.json()["detail"]["details"]["circuit"]["open"] is True
    assert attempts == ["https://analysis.internal/analyze"]

    after_metrics = client.get("/internal/analysis-provider/metrics", headers=auth_headers).json()["providers"][
        "external-http-analysis-v1"
    ]
    assert after_metrics["analyze_failures"] == before_metrics.get("analyze_failures", 0) + 2
    assert after_metrics["circuit_open_events"] >= before_metrics.get("circuit_open_events", 0) + 1
    assert after_metrics["last_status"] == "failure"


def test_clamav_scan_downloads_private_drive_asset(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "client-id")
    monkeypatch.setattr(settings, "google_client_secret", "client-secret")

    class FakeTokenResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "drive-access-token", "refresh_token": "refresh-token", "expires_in": 3600}

    monkeypatch.setattr("app.services.media.httpx.post", lambda url, data, timeout: FakeTokenResponse())

    project = client.post("/projects", json={"name": "Drive Scan"}, headers=auth_headers).json()
    connected = client.post(
        f"/projects/{project['id']}/connect-drive",
        json={"folder_url": "https://drive.google.com/drive/folders/private-folder-id"},
        headers=auth_headers,
    )
    state = parse_qs(urlparse(connected.json()["authorization_url"]).query)["state"][0]
    callback = client.get(f"/projects/{project['id']}/connect-drive/callback", params={"code": "oauth-code", "state": state})
    assert callback.status_code == 200
    ingested = client.post(
        f"/projects/{project['id']}/ingest",
        json={
            "assets": [
                {
                    "filename": "hero clip.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 10,
                    "private_locator": "drive://private-folder-id/video-1",
                }
            ]
        },
        headers=auth_headers,
    )
    media_asset_id = ingested.json()["accepted_asset_ids"][0]
    downloaded = {}

    class FakeDownloadResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        def iter_bytes(self, chunk_size):
            downloaded["chunk_size"] = chunk_size
            yield b"private"
            yield b" media"

    def fake_stream(method, url, headers, timeout):
        downloaded["method"] = method
        downloaded["url"] = url
        downloaded["headers"] = headers
        downloaded["timeout"] = timeout
        return FakeDownloadResponse()

    scanned = {}

    def fake_scan_stream(self, chunks):
        scanned["payload"] = b"".join(chunks)
        return ScanResult(status="clean", scanner="clamav", details={"response": "stream: OK"})

    monkeypatch.setattr("app.services.malware.httpx.stream", fake_stream)
    monkeypatch.setattr("app.services.malware.ClamAVScanner.scan_stream", fake_scan_stream)

    scan = client.post(f"/internal/media-assets/{media_asset_id}/scan", headers=auth_headers)
    assert scan.status_code == 204
    assert downloaded["method"] == "GET"
    assert downloaded["headers"]["Authorization"] == "Bearer drive-access-token"
    assert downloaded["url"].endswith("/video-1?alt=media")
    assert scanned["payload"] == b"private media"

    with SessionLocal() as db:
        asset = db.get(MediaAsset, media_asset_id)
        assert asset.malware_scan_status == "clean"
        assert asset.metadata_json["malware_scan"]["scanner"] == "clamav"


def test_clamav_infected_result_marks_project_failed(client, auth_headers, monkeypatch):
    project = client.post("/projects", json={"name": "Bad Scan"}, headers=auth_headers).json()
    ingested = client.post(
        f"/projects/{project['id']}/ingest",
        json={
            "assets": [
                {
                    "filename": "bad.mp4",
                    "mime_type": "video/mp4",
                    "size_bytes": 10,
                    "private_locator": "drive://private-folder-id/video-1",
                }
            ]
        },
        headers=auth_headers,
    )
    media_asset_id = ingested.json()["accepted_asset_ids"][0]
    infected = client.post(
        f"/internal/media-assets/{media_asset_id}/malware-scan",
        json={"status": "infected", "scanner": "clamav", "details": {"signature": "Eicar-Test-Signature"}},
        headers=auth_headers,
    )
    assert infected.status_code == 204

    with SessionLocal() as db:
        asset = db.get(MediaAsset, media_asset_id)
        project_row = db.get(Project, project["id"])
        assert asset.malware_scan_status == "infected"
        assert project_row.status == ProjectStatus.failed
