"""Project-scoped Photos Picker integration; private data stays encrypted locally."""
from __future__ import annotations

import base64
import hashlib
import math
import re
import secrets
import tempfile
import time
from datetime import timedelta
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode, urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import MediaAsset, PhotosConnection, PlanStatus, Project, ProjectStatus, TimelinePlan, utcnow
from app.services.local_media import upload_local_media
from app.services.media import decrypt_token_payload, encrypt_token_payload, hash_oauth_state
from video_shared import sanitize_filename

SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"
API = "https://photospicker.googleapis.com/v1"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class PhotosError(ValueError):
    pass


def client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=False, trust_env=False)


def configuration_errors() -> list[str]:
    missing = [key for key, value in (("GOOGLE_CLIENT_ID", settings.google_client_id),
               ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
               ("TOKEN_ENCRYPTION_KEY", settings.token_encryption_key)) if not value]
    if settings.token_encryption_key:
        try:
            Fernet(settings.token_encryption_key.encode())
        except (ValueError, TypeError):
            missing.append("valid TOKEN_ENCRYPTION_KEY")
    uri = urlsplit(settings.google_photos_redirect_uri)
    if (uri.scheme != "http" or uri.hostname not in {"localhost", "127.0.0.1"}
            or uri.path != "/oauth/google-photos/callback" or uri.query or uri.fragment or uri.username):
        missing.append("loopback GOOGLE_PHOTOS_REDIRECT_URI")
    return missing


def require_configuration() -> None:
    if configuration_errors():
        raise PhotosError("Google Photos needs local OAuth credentials and a valid independent encryption key")


def unpack(row: PhotosConnection) -> dict:
    require_configuration()
    try:
        return decrypt_token_payload(row.encrypted_data)
    except (InvalidToken, ValueError):
        raise PhotosError("Google Photos credentials cannot be decrypted with the configured key") from None


def save(row: PhotosConnection, data: dict) -> None:
    row.encrypted_data = encrypt_token_payload(data)


def request_json(method: str, url: str, **kwargs) -> dict:
    try:
        with client() as http:
            response = http.request(method, url, **kwargs)
        if method == "DELETE" and response.status_code in {404, 410}:
            return {}
        if response.status_code in {401, 403}:
            raise PhotosError("Google denied access; reconnect or check Photos Picker API configuration")
        if response.status_code in {404, 410}:
            raise PhotosError("Google selection expired; start a new selection")
        if not response.is_success:
            raise PhotosError("Google request failed; retry later")
        return response.json() if response.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, PhotosError):
            raise
        raise PhotosError("Google request could not be completed; retry later") from None


def token_data(payload: dict, previous: dict | None = None) -> dict:
    previous = previous or {}
    if set(payload.get("scope", SCOPE).split()) != {SCOPE} or not payload.get("access_token"):
        raise PhotosError("Google did not grant the requested Photos permission")
    expires = payload.get("expires_in", 0)
    if not isinstance(expires, (int, float)) or not math.isfinite(expires) or expires <= 0:
        raise PhotosError("Google returned an invalid token expiry")
    return {"access_token": payload["access_token"], "refresh_token": payload.get("refresh_token") or previous.get("refresh_token"),
            "expires_at": time.time() + expires}


def access_token(row: PhotosConnection, data: dict) -> str:
    token = data.get("token") or {}
    if token.get("expires_at", 0) <= time.time() + 60:
        if not token.get("refresh_token"):
            raise PhotosError("Google Photos authorization expired; reconnect")
        payload = request_json("POST", TOKEN_URL, data={"client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret, "refresh_token": token["refresh_token"], "grant_type": "refresh_token"})
        token = token_data(payload, token)
        data["token"] = token
        save(row, data)
    return token["access_token"]


def begin_oauth(db: Session, project_id: str) -> dict:
    require_configuration()
    row = db.get(PhotosConnection, project_id)
    if row and row.status not in {"disconnected", "pending_oauth", "oauth_failed"}:
        raise PhotosError("Disconnect the existing Photos connection before reconnecting")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    if row is None:
        row = PhotosConnection(project_id=project_id, encrypted_data="")
        db.add(row)
    row.status = "pending_oauth"
    row.state_hash = hash_oauth_state(state)
    row.state_expires_at = utcnow() + timedelta(minutes=10)
    save(row, {"verifier": verifier})
    db.commit()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return {"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.google_client_id, "redirect_uri": settings.google_photos_redirect_uri,
        "response_type": "code", "scope": SCOPE, "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "false", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})}


def finish_oauth(db: Session, state: str, code: str | None, denied: bool = False) -> None:
    require_configuration()
    row = db.query(PhotosConnection).filter(PhotosConnection.state_hash == hash_oauth_state(state),
                                          PhotosConnection.status == "pending_oauth").first()
    if row is None:
        raise PhotosError("OAuth state is invalid or already used")
    project = db.get(Project, row.project_id)
    if project is None or project.status == ProjectStatus.deleted:
        raise PhotosError("OAuth project is unavailable")
    data = unpack(row)
    claimed = db.query(PhotosConnection).filter(PhotosConnection.project_id == row.project_id,
        PhotosConnection.state_hash == hash_oauth_state(state), PhotosConnection.state_expires_at > utcnow()).update(
            {"state_hash": None, "status": "oauth_failed"}, synchronize_session=False)
    db.commit()
    if claimed != 1:
        raise PhotosError("OAuth state expired or already used")
    if denied or not code:
        save(row, {})
        db.commit()
        raise PhotosError("Google Photos consent was not completed")
    payload = request_json("POST", TOKEN_URL, data={"client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret, "code": code, "grant_type": "authorization_code",
        "redirect_uri": settings.google_photos_redirect_uri, "code_verifier": data["verifier"]})
    save(row, {"token": token_data(payload)})
    row.status = "connected"
    row.state_hash = None
    row.state_expires_at = None
    db.commit()


def acquire(db: Session, project_id: str) -> PhotosConnection:
    require_configuration()
    changed = db.query(PhotosConnection).filter(PhotosConnection.project_id == project_id,
        or_(PhotosConnection.lease_until.is_(None), PhotosConnection.lease_until < utcnow())).update(
            {"lease_until": utcnow() + timedelta(minutes=10)}, synchronize_session=False)
    db.commit()
    if changed != 1:
        raise PhotosError("Photos connection is missing or another operation is in progress")
    row = db.get(PhotosConnection, project_id)
    db.refresh(row)
    return row


def release(db: Session, row: PhotosConnection) -> None:
    row.lease_until = None
    db.commit()


def session_path(data: dict) -> str:
    session_id = (data.get("session") or {}).get("id")
    if not session_id:
        raise PhotosError("Start a Google Photos selection first")
    return API + "/sessions/" + quote(session_id, safe="")


def update_session(data: dict, session: dict) -> None:
    picker_uri = session.get("pickerUri")
    if not picker_uri:
        previous = data.get("session") or {}
        if (not session.get("mediaItemsSet") or not session.get("id")
                or session.get("id") != previous.get("id") or not previous.get("pickerUri")):
            raise PhotosError("Google returned an unexpected Picker address")
        picker_uri = previous["pickerUri"]
        session = {**session, "pickerUri": picker_uri}
    uri = urlsplit(picker_uri)
    if uri.scheme != "https" or uri.hostname != "photos.google.com" or uri.username or uri.port not in {None, 443}:
        raise PhotosError("Google returned an unexpected Picker address")
    if not session.get("id"):
        raise PhotosError("Google returned an invalid selection session")
    polling = session.get("pollingConfig") or {}
    def seconds(key, default):
        raw = str(polling.get(key, default))
        if not re.fullmatch(r"\d+(\.\d+)?s", raw):
            raise PhotosError("Google returned invalid polling settings")
        return float(raw[:-1])
    interval = max(1, seconds("pollInterval", "5s"))
    data["session"] = session
    data["next_poll_at"] = time.time() + interval
    data["poll_deadline"] = time.time() + min(seconds("timeoutIn", "600s"), 3600)


def status(db: Session, project_id: str) -> dict:
    missing = configuration_errors()
    row = db.get(PhotosConnection, project_id)
    if missing:
        return {"configured": False, "missing": missing, "status": "not_configured"}
    if row is None:
        return {"configured": True, "status": "disconnected"}
    data = unpack(row)
    session = data.get("session") or {}
    return {"configured": True, "status": row.status, "picker_url": session.get("pickerUri"),
            "selected_count": len(data.get("items", [])), "processed_count": data.get("cursor", 0),
            "imported_count": data.get("imported", 0), "skipped_count": data.get("skipped", 0),
            "error": data.get("error"), "poll_after_seconds": max(1, math.ceil(data.get("next_poll_at", 0) - time.time()))}


def create_selection(row: PhotosConnection, data: dict) -> None:
    if row.status not in {"connected", "complete"}:
        raise PhotosError("Finish or cancel the current selection first")
    token = access_token(row, data)
    token_data = data["token"]
    if data.get("session"):
        request_json("DELETE", session_path(data), headers={"Authorization": f"Bearer {token}"})
    session = request_json("POST", API + "/sessions", headers={"Authorization": f"Bearer {token}"},
                           json={"pickingConfig": {"maxItemCount": str(settings.max_project_media)}})
    data.clear()
    data["token"] = token_data
    update_session(data, session)
    row.status = "selecting"


def poll_selection(row: PhotosConnection, data: dict) -> None:
    if row.status != "selecting":
        return
    if time.time() < data.get("next_poll_at", 0):
        return
    if time.time() >= data.get("poll_deadline", 0):
        raise PhotosError("Picker polling timed out; cancel and start a new selection")
    token = access_token(row, data)
    session = request_json("GET", session_path(data), headers={"Authorization": f"Bearer {token}"})
    update_session(data, session)
    if session.get("mediaItemsSet"):
        row.status = "ready"


def list_items(token: str, session_id: str) -> list[dict]:
    items, seen_pages, seen_ids = [], set(), set()
    page = None
    for _ in range(10):
        params = {"sessionId": session_id, "pageSize": 100}
        if page:
            params["pageToken"] = page
        result = request_json("GET", API + "/mediaItems", headers={"Authorization": f"Bearer {token}"}, params=params)
        for item in result.get("mediaItems", []):
            if not item.get("id"):
                raise PhotosError("Google returned a media item without an identifier")
            if item["id"] not in seen_ids:
                items.append(item)
                seen_ids.add(item["id"])
            if len(items) > settings.max_project_media:
                raise PhotosError("Selection exceeds the local project media limit")
        page = result.get("nextPageToken")
        if not page:
            return items
        if page in seen_pages:
            break
        seen_pages.add(page)
    raise PhotosError("Google returned excessive or repeated pagination")


def download_url(item: dict) -> str:
    media = item.get("mediaFile") or {}
    url = media.get("baseUrl", "")
    parts = urlsplit(url)
    if (parts.scheme != "https" or not re.fullmatch(r"lh[1-6]\.googleusercontent\.com", parts.hostname or "")
            or parts.port not in {None, 443} or parts.username or parts.query or parts.fragment):
        raise PhotosError("Google returned an unsupported media download address")
    if item.get("type") == "VIDEO":
        video = (media.get("mediaFileMetadata") or {}).get("videoMetadata") or {}
        if video.get("processingStatus") != "READY":
            raise PhotosError("Google video is not ready; retry after processing completes")
        return url + "=dv"
    if item.get("type") == "PHOTO":
        return url + "=d"
    raise PhotosError("Unsupported Google Photos media type")


def import_item(db: Session, project_id: str, item: dict, token: str) -> bool:
    identity = hash_oauth_state(item["id"])
    existing = db.query(MediaAsset).filter(MediaAsset.project_id == project_id).all()
    if any((asset.metadata_json or {}).get("photos_item_hash") == identity for asset in existing):
        return False
    url = download_url(item)
    deadline = time.monotonic() + 120
    with tempfile.TemporaryFile() as spool:
        try:
            headers = {"Authorization": f"Bearer {token}"}
            with client() as http:
                for attempt in range(2):
                    with http.stream("GET", url, headers=headers) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            redirect = urlsplit(response.headers.get("location", ""))
                            if (attempt or redirect.scheme != "https"
                                    or redirect.hostname != "video-downloads.googleusercontent.com"
                                    or redirect.port not in {None, 443} or redirect.username or redirect.fragment):
                                raise PhotosError("Google returned an unsupported media download redirect")
                            url = response.headers["location"]
                            headers = {}
                            continue
                        if not response.is_success:
                            raise PhotosError("Media download failed or expired; retry to refresh the selection URLs")
                        size = 0
                        for chunk in response.iter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > settings.max_upload_bytes or time.monotonic() > deadline:
                                raise PhotosError("Media download exceeded the local size or time limit")
                            spool.write(chunk)
                        break
                else:
                    raise PhotosError("Google returned excessive media download redirects")
        except httpx.HTTPError:
            raise PhotosError("Media download interrupted; retry this item") from None
        spool.seek(0)
        remote_name = item["mediaFile"].get("filename") or "photo-media"
        filename = sanitize_filename(PurePosixPath(remote_name.replace("\\", "/")).name)
        media = upload_local_media(db, project_id=project_id, upload=UploadFile(file=spool, filename=filename))
    media.metadata_json = {**media.metadata_json, "source": "google_photos", "photos_item_hash": identity,
                           "capture_time": item.get("createTime")}
    for plan in db.query(TimelinePlan).filter(TimelinePlan.project_id == project_id,
                                             TimelinePlan.status == PlanStatus.approved).all():
        plan.status = PlanStatus.rejected
    db.get(Project, project_id).status = ProjectStatus.ingesting
    return True


def import_next(db: Session, row: PhotosConnection, data: dict) -> None:
    if row.status not in {"ready", "importing"}:
        raise PhotosError("Complete the Photos selection before importing")
    token = access_token(row, data)
    if not data.get("items") or data.get("error"):
        # Base URLs expire. Refresh from Google, keeping the original item order.
        fresh = list_items(token, data["session"]["id"])
        if data.get("items"):
            by_id = {item["id"]: item for item in fresh}
            data["items"] = [by_id.get(item["id"], item) for item in data["items"]]
        else:
            data["items"] = fresh
    cursor = data.get("cursor", 0)
    if cursor < len(data["items"]):
        imported = import_item(db, row.project_id, data["items"][cursor], token)
        data["cursor"] = cursor + 1
        key = "imported" if imported else "skipped"
        data[key] = data.get(key, 0) + 1
    data.pop("error", None)
    row.status = "importing"
    if data.get("cursor", 0) >= len(data["items"]):
        request_json("DELETE", session_path(data), headers={"Authorization": f"Bearer {token}"})
        data.pop("session", None)
        # Keep only non-URL identifiers for local progress, not expired base URLs.
        data["items"] = [{"id": item["id"]} for item in data["items"]]
        row.status = "complete"


def cancel_selection(row: PhotosConnection, data: dict) -> None:
    if data.get("session"):
        token = access_token(row, data)
        request_json("DELETE", session_path(data), headers={"Authorization": f"Bearer {token}"})
    token = data.get("token")
    data.clear()
    if token:
        data["token"] = token
    row.status = "connected" if token else "disconnected"


def disconnect(row: PhotosConnection, data: dict) -> None:
    token = data.get("token") or {}
    credential = token.get("refresh_token") or token.get("access_token")
    if credential:
        request_json("POST", "https://oauth2.googleapis.com/revoke", data={"token": credential})
    data.clear()
    row.status = "disconnected"
    row.state_hash = None
    row.state_expires_at = None
