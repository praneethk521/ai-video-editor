from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import MediaAsset
from app.services.malware import ClamAVScanner
from app.services.media import create_media_asset
from video_shared.media import probe_media, safe_component


def upload_local_media(db: Session, *, project_id: str, upload: UploadFile) -> MediaAsset:
    if db.query(MediaAsset).filter(MediaAsset.project_id == project_id).count() >= settings.max_project_media:
        raise ValueError("project media limit reached")
    if settings.malware_scanner_backend != "clamav":
        raise ValueError("local uploads require ClamAV")
    directory = Path(settings.media_source_root) / safe_component(project_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / uuid4().hex
    checksum = hashlib.sha256()
    size = 0
    try:
        with path.open("xb") as output:
            path.chmod(0o600)
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise ValueError("file exceeds configured upload size limit")
                checksum.update(chunk)
                output.write(chunk)
        if not size:
            raise ValueError("empty file")
        with path.open("rb") as source:
            scan = ClamAVScanner(settings.clamav_host, settings.clamav_port).scan_stream(
                iter(lambda: source.read(1024 * 1024), b"")
            )
        if scan.status != "clean":
            raise ValueError("file did not pass malware scanning")
        metadata = probe_media(path, settings.ffprobe_path)
        media = create_media_asset(db, project_id=project_id, asset=SimpleNamespace(
            filename=upload.filename or "media", size_bytes=size,
            private_locator=f"file://private/sources/{project_id}/{path.name}",
            content_checksum=checksum.hexdigest(), **metadata,
        ))
        media.malware_scan_status = "clean"
        media.metadata_json = {**metadata, "source": "local_upload", "relative_path": f"{project_id}/{path.name}",
                               "sha256": checksum.hexdigest(), "malware_scan": {"scanner": "clamav", "status": "clean"}}
        db.flush()
        return media
    except (OSError, subprocess.SubprocessError) as exc:
        path.unlink(missing_ok=True)
        raise ValueError("upload processing failed; check scanner availability and media encoding") from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise


def media_thumbnail(asset: MediaAsset) -> bytes:
    from video_shared.media import source_path

    metadata = asset.metadata_json or {}
    path = source_path(Path(settings.media_source_root), asset.project_id, metadata.get("relative_path", ""))
    timestamp = min(max(0, float(metadata.get("recommended_start", 0))), max(0, asset.duration_seconds - 0.1))
    try:
        result = subprocess.run(
            [
                settings.ffmpeg_path,
                "-v", "error",
                "-nostdin",
                "-protocol_whitelist", "file,pipe",
                "-ss", str(timestamp),
                "-i", str(path),
                "-vf", "scale=480:320:force_original_aspect_ratio=decrease,pad=480:320:(ow-iw)/2:(oh-ih)/2:color=black",
                "-frames:v", "1",
                "-threads", "1",
                "-q:v", "5",
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("could not create media thumbnail") from exc
    if not result.stdout.startswith(b"\xff\xd8") or len(result.stdout) > 1024 * 1024:
        raise ValueError("could not create media thumbnail")
    return result.stdout
