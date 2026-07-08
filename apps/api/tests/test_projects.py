from __future__ import annotations

from urllib.parse import parse_qs, urlparse

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


def test_requires_authentication(client):
    response = client.post("/projects", json={"name": "Nope"})
    assert response.status_code == 401


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
    captured = {}

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
