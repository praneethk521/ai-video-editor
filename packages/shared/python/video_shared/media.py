from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def safe_component(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("invalid private storage identifier")
    return value


def source_path(root: Path, project_id: str, relative_path: str) -> Path:
    project_root = root.resolve() / safe_component(project_id)
    candidate = (root / relative_path).resolve()
    if candidate.parent != project_root or not candidate.is_file():
        raise ValueError("source is missing or outside the project storage directory")
    return candidate


def probe_media(path: Path, ffprobe: str = "ffprobe") -> dict:
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
         "-format_whitelist", "image2,jpeg_pipe,png_pipe,webp_pipe,mov,matroska,webm",
         "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("a supported image or video stream is required")
    width, height = int(video["width"]), int(video["height"])
    if width < 1 or height < 1 or width * height > 50_000_000:
        raise ValueError("media dimensions exceed the supported limit")
    container = payload.get("format", {}).get("format_name", "")
    is_image = container in {"image2", "jpeg_pipe", "png_pipe", "webp_pipe"}
    codec = video.get("codec_name", "")
    if is_image:
        mime = {"mjpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(codec)
        duration = 3.0
    else:
        mime = "video/webm" if "webm" in container else "video/mp4"
        duration = float(payload.get("format", {}).get("duration") or video.get("duration") or 0)
        if not 0 < duration <= 3600:
            raise ValueError("video duration must be between zero and one hour")
    if not mime:
        raise ValueError("unsupported image encoding")
    return {"mime_type": mime, "duration_seconds": duration, "width": width, "height": height,
            "orientation": "landscape" if width >= height else "portrait",
            "has_audio": any(stream.get("codec_type") == "audio" for stream in streams)}
