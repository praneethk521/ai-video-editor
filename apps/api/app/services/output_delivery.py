from __future__ import annotations

import json
import mimetypes
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import OutputVideo
from app.services.media import decrypt_token_payload, latest_connected_drive_connection


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

from video_shared import validate_private_locator  # noqa: E402


ALLOWED_DELIVERY_TARGETS = {"drive", "s3", "local_private"}
ALLOWED_DELIVERY_STATUSES = {"private_staging", "pending_private_delivery", "delivered", "failed"}


@dataclass(frozen=True)
class DeliveryResult:
    target: str
    status: str
    delivered_locator: str
    details: dict


def deliver_output_video(db: Session, *, output_video_id: str, target: str | None = None) -> OutputVideo:
    output = db.get(OutputVideo, output_video_id)
    if output is None:
        raise ValueError("output video not found")
    delivery_target = target or output.delivery_target
    if delivery_target not in ALLOWED_DELIVERY_TARGETS:
        raise ValueError("unsupported output delivery target")

    source_path = resolve_private_file_locator(output.private_locator)
    if delivery_target == "drive":
        result = deliver_to_drive(db, output=output, source_path=source_path)
    elif delivery_target == "s3":
        result = deliver_to_s3(output=output, source_path=source_path)
    else:
        result = deliver_to_local_private(output=output, source_path=source_path)

    delivered_output = record_output_delivery(
        db,
        output_video_id=output_video_id,
        target=result.target,
        status=result.status,
        delivered_locator=result.delivered_locator,
        details=result.details,
    )
    if settings.cleanup_staged_outputs_after_delivery:
        append_delivery_lifecycle_detail(
            delivered_output,
            "staged_source_cleanup",
            cleanup_staged_output_source(source_path=source_path),
        )
    return delivered_output


def record_output_delivery_failure(
    db: Session,
    *,
    output_video_id: str,
    target: str | None,
    error_message: str,
    phase: str,
) -> OutputVideo | None:
    output = db.get(OutputVideo, output_video_id)
    if output is None:
        return None
    return record_output_delivery(
        db,
        output_video_id=output_video_id,
        target=target or output.delivery_target,
        status="failed",
        delivered_locator=None,
        details={"error": error_message[:1000], "phase": phase},
    )


def record_output_delivery(
    db: Session,
    *,
    output_video_id: str,
    target: str,
    status: str,
    delivered_locator: str | None,
    details: dict,
) -> OutputVideo:
    output = db.get(OutputVideo, output_video_id)
    if output is None:
        raise ValueError("output video not found")
    if target not in ALLOWED_DELIVERY_TARGETS:
        raise ValueError("unsupported output delivery target")
    if status not in ALLOWED_DELIVERY_STATUSES:
        raise ValueError("unsupported output delivery status")
    if status == "delivered" and not delivered_locator:
        raise ValueError("delivered outputs require a private delivered locator")

    output.delivery_target = target
    output.delivery_status = status
    if delivered_locator is not None:
        output.delivered_locator = validate_private_locator(delivered_locator)
    output.delivery_json = {
        **(output.delivery_json or {}),
        "target": target,
        "status": status,
        "details": details,
    }
    return output


def append_delivery_lifecycle_detail(output: OutputVideo, key: str, detail: dict) -> None:
    output.delivery_json = {
        **(output.delivery_json or {}),
        key: detail,
    }


def cleanup_staged_output_source(*, source_path: Path) -> dict:
    try:
        if not source_path.exists():
            return {"status": "skipped", "reason": "source_missing"}
        source_path.unlink()
        return {"status": "deleted"}
    except OSError as exc:
        return {"status": "failed", "error": str(exc)[:1000]}


def retention_metadata() -> dict[str, str]:
    retention_days = max(1, settings.delivered_output_retention_days)
    delete_after = (datetime.now(timezone.utc) + timedelta(days=retention_days)).date().isoformat()
    return {
        "privacy": "private",
        "retention_policy": settings.delivered_output_retention_policy,
        "retention_days": str(retention_days),
        "delete_after": delete_after,
    }


def resolve_private_file_locator(locator: str) -> Path:
    validate_private_locator(locator)
    prefix = "file://private/"
    if not locator.startswith(prefix):
        raise ValueError("output delivery requires a staged file://private source locator")
    relative = Path(locator.removeprefix(prefix))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("output source locator is unsafe")
    root = Path(settings.output_delivery_local_root).resolve()
    source_path = (root / relative).resolve()
    if root not in source_path.parents and source_path != root:
        raise ValueError("output source locator escapes delivery root")
    if not source_path.is_file():
        raise ValueError("staged output file is missing")
    return source_path


def deliver_to_drive(db: Session, *, output: OutputVideo, source_path: Path) -> DeliveryResult:
    connection = latest_connected_drive_connection(db, project_id=output.project_id)
    if connection is None or not connection.encrypted_token_json:
        raise ValueError("project does not have a connected Drive account for output delivery")
    token_payload = decrypt_token_payload(connection.encrypted_token_json)
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ValueError("Drive OAuth token is missing an access token")
    folder_id = settings.google_drive_output_folder_id or connection.selected_folder_id
    if not folder_id:
        raise ValueError("Drive output folder id is missing")

    file_name = f"{output.variant}-{output.id}.mp4"
    retention = retention_metadata()
    metadata = {"name": file_name, "parents": [folder_id], "appProperties": retention}
    content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    body, boundary = build_drive_multipart_body(metadata=metadata, source_path=source_path, content_type=content_type)
    response = httpx.post(
        settings.google_drive_upload_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        content=body,
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    drive_file_id = payload.get("id")
    if not drive_file_id:
        raise ValueError("Drive upload response did not include an id")
    return DeliveryResult(
        target="drive",
        status="delivered",
        delivered_locator=f"drive://{folder_id}/{drive_file_id}",
        details={"provider": "google_drive", "drive_file_id": drive_file_id, "folder_id": folder_id, "retention": retention},
    )


def build_drive_multipart_body(*, metadata: dict, source_path: Path, content_type: str) -> tuple[bytes, str]:
    boundary = f"codex-ai-video-editor-{uuid4().hex}"
    metadata_json = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
    file_bytes = source_path.read_bytes()
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
            metadata_json,
            b"\r\n",
            f"--{boundary}\r\n".encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return body, boundary


def deliver_to_s3(*, output: OutputVideo, source_path: Path) -> DeliveryResult:
    if not settings.s3_bucket:
        raise ValueError("S3_BUCKET is required for S3 output delivery")
    key = s3_output_key(output=output, source_path=source_path)
    extra_args = {
        "Bucket": settings.s3_bucket,
        "Key": key,
        "ContentType": mimetypes.guess_type(source_path.name)[0] or "application/octet-stream",
    }
    retention = retention_metadata()
    extra_args["Tagging"] = urlencode(retention)
    if settings.media_encryption_kms_key_id:
        extra_args["ServerSideEncryption"] = "aws:kms"
        extra_args["SSEKMSKeyId"] = settings.media_encryption_kms_key_id
    else:
        extra_args["ServerSideEncryption"] = "AES256"
    with source_path.open("rb") as handle:
        _s3_client().put_object(Body=handle, **extra_args)
    return DeliveryResult(
        target="s3",
        status="delivered",
        delivered_locator=f"s3://private/{settings.s3_bucket}/{key}",
        details={"provider": "s3", "bucket": settings.s3_bucket, "key": key, "retention": retention},
    )


def s3_output_key(*, output: OutputVideo, source_path: Path) -> str:
    prefix = settings.s3_prefix.strip("/")
    filename = f"{output.variant}-{output.id}{source_path.suffix or '.mp4'}"
    return "/".join(part for part in [prefix, output.project_id, filename] if part)


def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise ValueError("boto3 is required for S3 output delivery") from exc
    return boto3.client("s3", region_name=settings.s3_region)


def deliver_to_local_private(*, output: OutputVideo, source_path: Path) -> DeliveryResult:
    destination_root = Path(settings.local_private_delivery_root).resolve()
    destination_dir = destination_root / output.project_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{output.variant}-{output.id}{source_path.suffix or '.mp4'}"
    shutil.copy2(source_path, destination)
    retention = retention_metadata()
    delivered_locator = f"file://private/delivered/{output.project_id}/{destination.name}"
    sidecar = destination.with_name(f"{destination.name}.retention.json")
    sidecar.write_text(
        json.dumps({"delivered_locator": delivered_locator, "retention": retention}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return DeliveryResult(
        target="local_private",
        status="delivered",
        delivered_locator=delivered_locator,
        details={
            "provider": "local_private",
            "path": str(destination),
            "retention": retention,
            "retention_sidecar": f"file://private/delivered/{output.project_id}/{sidecar.name}",
        },
    )
