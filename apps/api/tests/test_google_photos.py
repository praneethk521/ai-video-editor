from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.security import CurrentUser, get_current_user
from app.models.entities import PhotosConnection, Project, ProjectMember
from app.services import google_photos as photos
from app.services.media import encrypt_token_payload


@pytest.fixture
def photos_config(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "local-client.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "local-secret")
    monkeypatch.setattr(settings, "token_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "google_photos_redirect_uri", "http://localhost:8001/oauth/google-photos/callback")


@pytest.fixture
def photos_project(db_session, photos_config):
    project = Project(name="Photos", owner_user_id="owner-user")
    db_session.add(project)
    db_session.commit()
    return project


def token_payload():
    return {"access_token": "photos-access", "refresh_token": "photos-refresh", "expires_in": 3600,
            "scope": photos.SCOPE}


def connected(db_session, project):
    row = PhotosConnection(project_id=project.id, status="connected",
                           encrypted_data=encrypt_token_payload({"token": photos.token_data(token_payload())}))
    db_session.add(row)
    db_session.commit()
    return row


def session_payload(*, ready=False):
    return {"id": "picker-session", "pickerUri": "https://photos.google.com/picker/session",
            "pollingConfig": {"pollInterval": "1s", "timeoutIn": "300s"}, "mediaItemsSet": ready}


def item(item_id="photo-1"):
    return {"id": item_id, "type": "PHOTO", "createTime": "2026-01-02T03:04:05Z",
            "mediaFile": {"baseUrl": "https://lh3.googleusercontent.com/p/media", "mimeType": "image/jpeg",
                          "filename": "trip.jpg", "mediaFileMetadata": {"width": 100, "height": 50}}}


def test_unconfigured_status_is_actionable(client, auth_headers):
    project_id = client.post("/projects", headers=auth_headers, json={"name": "Photos"}).json()["id"]
    response = client.get(f"/projects/{project_id}/photos", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "GOOGLE_CLIENT_ID" in response.json()["missing"]


def test_oauth_uses_pkce_exact_scope_and_one_use_state(db_session, photos_project, monkeypatch):
    started = photos.begin_oauth(db_session, photos_project.id)
    query = parse_qs(urlparse(started["authorization_url"]).query)
    state = query["state"][0]
    assert query["scope"] == [photos.SCOPE]
    assert query["code_challenge_method"] == ["S256"]
    monkeypatch.setattr(photos, "request_json", lambda *args, **kwargs: token_payload())
    photos.finish_oauth(db_session, state, "authorization-code")
    row = db_session.get(PhotosConnection, photos_project.id)
    assert row.status == "connected"
    assert photos.unpack(row)["token"]["refresh_token"] == "photos-refresh"
    with pytest.raises(photos.PhotosError, match="invalid or already used"):
        photos.finish_oauth(db_session, state, "replayed-code")


def test_picker_poll_and_paginated_listing(db_session, photos_project, monkeypatch):
    row = connected(db_session, photos_project)
    calls = []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("params")))
        if method == "POST":
            return session_payload()
        if "/sessions/" in url:
            return session_payload(ready=True)
        return {"mediaItems": [item("photo-1")], "nextPageToken": "next"} if not kwargs["params"].get("pageToken") else {
            "mediaItems": [item("photo-1"), item("photo-2")]}
    monkeypatch.setattr(photos, "request_json", request)
    data = photos.unpack(row)
    photos.create_selection(row, data)
    assert row.status == "selecting"
    assert data["session"]["pickerUri"].startswith("https://photos.google.com/")
    data["next_poll_at"] = 0
    photos.poll_selection(row, data)
    assert row.status == "ready"
    assert [entry["id"] for entry in photos.list_items("token", "picker-session")] == ["photo-1", "photo-2"]
    assert calls[-1][2]["pageToken"] == "next"


def test_completed_picker_poll_can_omit_expired_picker_uri(db_session, photos_project, monkeypatch):
    row = connected(db_session, photos_project)
    data = photos.unpack(row)
    original_session = session_payload()
    photos.update_session(data, original_session)
    row.status = "selecting"
    data["next_poll_at"] = 0

    completed = {key: value for key, value in session_payload(ready=True).items() if key != "pickerUri"}
    monkeypatch.setattr(photos, "request_json", lambda *args, **kwargs: completed)

    photos.poll_selection(row, data)

    assert row.status == "ready"
    assert data["session"]["pickerUri"] == original_session["pickerUri"]


def test_expired_token_refreshes_without_losing_refresh_token(db_session, photos_project, monkeypatch):
    row = connected(db_session, photos_project)
    data = photos.unpack(row)
    data["token"]["expires_at"] = 0
    monkeypatch.setattr(photos, "request_json", lambda *args, **kwargs: {
        "access_token": "refreshed-access", "expires_in": 1800, "scope": photos.SCOPE})
    assert photos.access_token(row, data) == "refreshed-access"
    assert data["token"]["refresh_token"] == "photos-refresh"


@pytest.mark.parametrize("url", [
    "http://lh3.googleusercontent.com/p/media",
    "https://example.com/p/media",
    "https://lh3.googleusercontent.com.evil.test/p/media",
    "https://lh3.googleusercontent.com:444/p/media",
])
def test_download_url_rejects_untrusted_hosts(url):
    payload = item()
    payload["mediaFile"]["baseUrl"] = url
    with pytest.raises(photos.PhotosError, match="unsupported media download"):
        photos.download_url(payload)


def test_import_progress_resumes_and_scrubs_expiring_urls(db_session, photos_project, monkeypatch):
    row = connected(db_session, photos_project)
    row.status = "ready"
    data = photos.unpack(row)
    data["session"] = session_payload(ready=True)
    imported = []
    monkeypatch.setattr(photos, "list_items", lambda *args: [item("one"), item("two")])
    monkeypatch.setattr(photos, "import_item", lambda db, project_id, media, token: imported.append(media["id"]) or True)
    monkeypatch.setattr(photos, "request_json", lambda *args, **kwargs: {})
    photos.import_next(db_session, row, data)
    assert data["cursor"] == 1 and row.status == "importing"
    photos.save(row, data)
    db_session.commit()
    resumed = photos.unpack(db_session.get(PhotosConnection, photos_project.id))
    photos.import_next(db_session, row, resumed)
    assert imported == ["one", "two"]
    assert row.status == "complete"
    assert resumed["items"] == [{"id": "one"}, {"id": "two"}]
    assert "pickerUri" not in str(resumed)


def test_import_item_streams_bytes_into_private_local_ingest(db_session, photos_project, monkeypatch):
    class Response:
        status_code = 200
        is_success = True
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_bytes(self, size): yield b"private-photo-bytes"
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args, **kwargs): return Response()
    captured = {}
    def upload(db, project_id, upload):
        captured["project_id"] = project_id
        captured["filename"] = upload.filename
        captured["bytes"] = upload.file.read()
        return SimpleNamespace(metadata_json={})
    monkeypatch.setattr(photos, "client", Client)
    monkeypatch.setattr(photos, "upload_local_media", upload)
    payload = item()
    payload["mediaFile"]["filename"] = "../unsafe trip.jpg"
    assert photos.import_item(db_session, photos_project.id, payload, "token") is True
    assert captured == {"project_id": photos_project.id, "filename": "unsafe_trip.jpg", "bytes": b"private-photo-bytes"}


def test_video_download_follows_only_trusted_google_redirect_without_bearer(
        db_session, photos_project, monkeypatch):
    class Response:
        def __init__(self, status_code, headers=None, body=b""):
            self.status_code = status_code
            self.headers = headers or {}
            self.is_success = status_code == 200
            self.body = body
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_bytes(self, size): yield self.body
    class Client:
        calls = []
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, method, url, headers):
            self.calls.append((url, headers))
            if len(self.calls) == 1:
                return Response(302, {"location": "https://video-downloads.googleusercontent.com/video"})
            return Response(200, body=b"private-video-bytes")
    monkeypatch.setattr(photos, "client", Client)
    monkeypatch.setattr(photos, "upload_local_media", lambda *args, **kwargs: SimpleNamespace(metadata_json={}))
    payload = item()
    payload["type"] = "VIDEO"
    payload["mediaFile"]["filename"] = "trip.mov"
    payload["mediaFile"]["mediaFileMetadata"] = {"videoMetadata": {"processingStatus": "READY"}}

    assert photos.import_item(db_session, photos_project.id, payload, "token") is True
    assert Client.calls[0][1] == {"Authorization": "Bearer token"}
    assert Client.calls[1] == ("https://video-downloads.googleusercontent.com/video", {})


def test_video_download_rejects_untrusted_redirect(db_session, photos_project, monkeypatch):
    class Response:
        status_code = 302
        is_success = False
        headers = {"location": "https://evil.test/video"}
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args, **kwargs): return Response()
    monkeypatch.setattr(photos, "client", Client)
    payload = item()
    payload["type"] = "VIDEO"
    payload["mediaFile"]["mediaFileMetadata"] = {"videoMetadata": {"processingStatus": "READY"}}

    with pytest.raises(photos.PhotosError, match="unsupported media download redirect"):
        photos.import_item(db_session, photos_project.id, payload, "token")


def test_invalid_picker_uri_and_video_processing_are_rejected():
    with pytest.raises(photos.PhotosError, match="unexpected Picker"):
        photos.update_session({}, {**session_payload(), "pickerUri": "https://evil.test/picker"})
    existing = {"session": session_payload()}
    with pytest.raises(photos.PhotosError, match="unexpected Picker"):
        photos.update_session(existing, {"id": "different-session", "mediaItemsSet": True})
    video = item()
    video["type"] = "VIDEO"
    video["mediaFile"]["mediaFileMetadata"] = {"videoMetadata": {"processingStatus": "PROCESSING"}}
    with pytest.raises(photos.PhotosError, match="not ready"):
        photos.download_url(video)


def test_non_owner_cannot_read_photos_status(client, auth_headers, db_session, photos_project):
    db_session.add(ProjectMember(project_id=photos_project.id, user_id="viewer-user", role="viewer"))
    db_session.commit()

    def viewer_user():
        return CurrentUser("viewer-user", "viewer@example.test")

    client.app.dependency_overrides[get_current_user] = viewer_user
    try:
        response = client.get(f"/projects/{photos_project.id}/photos", headers=auth_headers)
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 403
