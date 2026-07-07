from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import MediaAsset, OAuthConnection

from pathlib import Path
import sys

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


def hash_folder_url(folder_url: str) -> str:
    return hashlib.sha256(folder_url.encode("utf-8")).hexdigest()


def create_drive_connection(db: Session, *, project_id: str, folder_url: str) -> OAuthConnection:
    connection = OAuthConnection(
        project_id=project_id,
        folder_url_hash=hash_folder_url(folder_url),
        scopes=settings.google_drive_scopes,
        status="pending_oauth",
    )
    db.add(connection)
    return connection


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
        malware_scan_status="clean",
        metadata_json={"source": "api_ingest"},
    )
    db.add(media)
    return media
