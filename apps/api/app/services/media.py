from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import desc

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import MediaAsset, OAuthConnection, utcnow

import sys
from pathlib import Path

def add_shared_path() -> None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "shared" / "python"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))
            return
    container_candidate = Path("/packages/shared/python")
    if container_candidate.exists() and str(container_candidate) not in sys.path:
        sys.path.append(str(container_candidate))


add_shared_path()

from video_shared import sanitize_filename, validate_private_locator  # noqa: E402

DRIVE_FOLDER_PATTERNS = (
    re.compile(r"/drive/folders/([^/?#]+)"),
    re.compile(r"[?&]id=([^&#]+)"),
)


def hash_folder_url(folder_url: str) -> str:
    return hashlib.sha256(folder_url.encode("utf-8")).hexdigest()


def hash_oauth_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def extract_drive_folder_id(folder_url: str) -> str | None:
    for pattern in DRIVE_FOLDER_PATTERNS:
        match = pattern.search(folder_url)
        if match:
            return match.group(1)
    return None


def create_drive_connection(db: Session, *, project_id: str, folder_url: str) -> tuple[OAuthConnection, str]:
    state = secrets.token_urlsafe(32)
    connection = OAuthConnection(
        project_id=project_id,
        folder_url_hash=hash_folder_url(folder_url),
        selected_folder_id=extract_drive_folder_id(folder_url),
        scopes=settings.google_drive_scopes,
        status="pending_oauth",
        oauth_state_hash=hash_oauth_state(state),
    )
    db.add(connection)
    db.flush()
    return connection, build_google_authorization_url(project_id=project_id, state=state)


def build_google_authorization_url(*, project_id: str, state: str) -> str:
    redirect_uri = settings.google_oauth_redirect_uri.format(project_id=project_id)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": settings.google_drive_scopes,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{settings.google_oauth_authorize_url}?{urlencode(params)}"


def complete_drive_oauth(db: Session, *, project_id: str, state: str, code: str) -> OAuthConnection:
    connection = (
        db.query(OAuthConnection)
        .filter(
            OAuthConnection.project_id == project_id,
            OAuthConnection.oauth_state_hash == hash_oauth_state(state),
            OAuthConnection.status == "pending_oauth",
        )
        .order_by(desc(OAuthConnection.created_at))
        .first()
    )
    if connection is None:
        raise ValueError("OAuth connection not found or state is invalid")

    token_payload = exchange_google_oauth_code(project_id=project_id, code=code)
    encrypted_token_json = encrypt_token_payload(token_payload)
    connection.encrypted_token_json = encrypted_token_json
    connection.token_expires_at = token_expiration(token_payload)
    connection.status = "connected"
    connection.connected_at = utcnow()
    connection.oauth_state_hash = None
    return connection


def exchange_google_oauth_code(*, project_id: str, code: str) -> dict:
    if not settings.google_client_id or not settings.google_client_secret:
        raise ValueError("Google OAuth client credentials are not configured")
    redirect_uri = settings.google_oauth_redirect_uri.format(project_id=project_id)
    response = httpx.post(
        settings.google_oauth_token_url,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "access_token" not in payload:
        raise ValueError("Google OAuth token response did not include an access token")
    return payload


def encryption_key() -> bytes:
    if settings.token_encryption_key:
        return settings.token_encryption_key.encode("utf-8")
    if settings.app_env not in {"local", "test"}:
        raise ValueError("TOKEN_ENCRYPTION_KEY must be configured outside local/test")
    digest = hashlib.sha256(settings.api_token.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_token_payload(payload: dict) -> str:
    token_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return Fernet(encryption_key()).encrypt(token_json).decode("utf-8")


def decrypt_token_payload(encrypted_payload: str) -> dict:
    token_json = Fernet(encryption_key()).decrypt(encrypted_payload.encode("utf-8"))
    return json.loads(token_json)


def token_expiration(payload: dict):
    expires_in = payload.get("expires_in")
    if not isinstance(expires_in, int) or expires_in <= 0:
        return None
    return utcnow() + timedelta(seconds=expires_in)


def validate_asset_payload(asset) -> tuple[str, str]:
    if asset.mime_type not in settings.allowed_media_mimes:
        raise ValueError(f"unsupported MIME type: {asset.mime_type}")
    if asset.size_bytes > settings.max_upload_bytes:
        raise ValueError("file exceeds configured upload size limit")
    safe_name = sanitize_filename(asset.filename)
    private_locator = validate_private_locator(asset.private_locator)
    return safe_name, private_locator


def create_media_asset(db: Session, *, project_id: str, asset) -> MediaAsset:
    safe_name, private_locator = validate_asset_payload(asset)
    media = MediaAsset(
        project_id=project_id,
        original_filename=asset.filename,
        sanitized_filename=safe_name,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        duration_seconds=asset.duration_seconds,
        orientation=asset.orientation,
        private_locator=private_locator,
        content_checksum=getattr(asset, "content_checksum", None),
        malware_scan_status="pending",
        metadata_json={"source": "api_ingest"},
    )
    db.add(media)
    return media


def sync_drive_folder(db: Session, *, project_id: str) -> dict:
    connection = latest_connected_drive_connection(db, project_id=project_id)
    if connection is None:
        raise ValueError("project does not have a connected Drive folder")
    if not connection.selected_folder_id:
        raise ValueError("Drive folder id is missing")
    token_payload = decrypt_token_payload(connection.encrypted_token_json or "")
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ValueError("Drive OAuth token is missing an access token")

    discovered = 0
    accepted_ids: list[str] = []
    duplicate_count = 0
    skipped_count = 0
    for drive_file in list_drive_folder_files(folder_id=connection.selected_folder_id, access_token=access_token):
        discovered += 1
        asset = drive_file_to_ingest_asset(connection.selected_folder_id, drive_file)
        if asset is None:
            skipped_count += 1
            continue
        if is_duplicate_media_asset(db, project_id=project_id, content_checksum=asset.content_checksum):
            duplicate_count += 1
            continue
        try:
            media = create_media_asset(db, project_id=project_id, asset=asset)
        except ValueError:
            skipped_count += 1
            continue
        media.metadata_json = {
            "source": "google_drive",
            "drive_file_id": drive_file["id"],
            "drive_mime_type": drive_file.get("mimeType"),
        }
        db.flush()
        accepted_ids.append(media.id)

    return {
        "discovered_count": discovered,
        "accepted_asset_ids": accepted_ids,
        "duplicate_count": duplicate_count,
        "skipped_count": skipped_count,
    }


def latest_connected_drive_connection(db: Session, *, project_id: str) -> OAuthConnection | None:
    return (
        db.query(OAuthConnection)
        .filter(
            OAuthConnection.project_id == project_id,
            OAuthConnection.provider == "google_drive",
            OAuthConnection.status == "connected",
        )
        .order_by(desc(OAuthConnection.connected_at), desc(OAuthConnection.created_at))
        .first()
    )


def list_drive_folder_files(*, folder_id: str, access_token: str) -> list[dict]:
    files: list[dict] = []
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken,files(id,name,mimeType,size,md5Checksum,videoMediaMetadata,imageMediaMetadata)",
            "pageSize": 1000,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        response = httpx.get(
            settings.google_drive_files_url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        files.extend(payload.get("files", []))
        page_token = payload.get("nextPageToken")
        if not page_token:
            return files


def drive_file_to_ingest_asset(folder_id: str, drive_file: dict):
    file_id = drive_file.get("id")
    filename = drive_file.get("name")
    mime_type = drive_file.get("mimeType")
    size = int(drive_file.get("size") or 0)
    if not file_id or not filename or not mime_type or size <= 0:
        return None

    video_metadata = drive_file.get("videoMediaMetadata") or {}
    image_metadata = drive_file.get("imageMediaMetadata") or {}
    duration_millis = int(video_metadata.get("durationMillis") or 0)
    width = int(video_metadata.get("width") or image_metadata.get("width") or 0)
    height = int(video_metadata.get("height") or image_metadata.get("height") or 0)
    orientation = "unknown"
    if width > 0 and height > 0:
        orientation = "landscape" if width >= height else "portrait"

    return SimpleNamespace(
        filename=filename,
        mime_type=mime_type,
        size_bytes=size,
        duration_seconds=round(duration_millis / 1000, 2) if duration_millis else 0,
        orientation=orientation,
        private_locator=f"drive://{folder_id}/{file_id}",
        content_checksum=drive_file.get("md5Checksum"),
    )


def is_duplicate_media_asset(db: Session, *, project_id: str, content_checksum: str | None) -> bool:
    if not content_checksum:
        return False
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id, MediaAsset.content_checksum == content_checksum)
        .first()
        is not None
    )
