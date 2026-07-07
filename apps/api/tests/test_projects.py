from __future__ import annotations


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

    analyzed = client.post(f"/projects/{project_id}/analyze", headers=auth_headers)
    assert analyzed.status_code == 200
    assert len(analyzed.json()["timeline_plan_ids"]) == 2

    rendered = client.post(f"/projects/{project_id}/render", json={"variants": ["youtube_16x9", "shorts_9x16"]}, headers=auth_headers)
    assert rendered.status_code == 200
    assert len(rendered.json()["render_job_ids"]) == 2

    status = client.get(f"/projects/{project_id}/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["status"] == "rendering"
    assert status.json()["media_count"] == 1


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

