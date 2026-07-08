from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.config import settings


class OutputValidationError(RuntimeError):
    def __init__(self, message: str, validation: dict):
        super().__init__(message)
        self.validation = validation


def skipped_validation(reason: str) -> dict:
    return {
        "status": "skipped",
        "reason": reason,
        "checks": {},
    }


def validate_output_file(
    path: Path,
    *,
    expected_width: int,
    expected_height: int,
    expected_duration_seconds: float,
    require_audio: bool = True,
) -> dict:
    command = [
        settings.ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    validation = {
        "status": "failed",
        "checks": {
            "file_exists": path.exists(),
            "file_size": path.exists() and path.stat().st_size > 0,
        },
        "ffprobe": {},
    }
    if not validation["checks"]["file_exists"] or not validation["checks"]["file_size"]:
        raise OutputValidationError("render output file is missing or empty", validation)

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=settings.max_job_seconds,
        )
        probe = json.loads(completed.stdout)
    except (json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        validation["error"] = getattr(exc, "stderr", None) or str(exc)
        raise OutputValidationError("ffprobe could not inspect render output", validation) from exc

    summary = summarize_ffprobe(probe)
    duration_tolerance = max(1.0, expected_duration_seconds * 0.05)
    validation["ffprobe"] = summary
    validation["checks"].update(
        {
            "video_stream": summary["has_video"],
            "resolution": summary["width"] == expected_width and summary["height"] == expected_height,
            "duration": (
                summary["duration_seconds"] > 0
                and abs(summary["duration_seconds"] - expected_duration_seconds) <= duration_tolerance
            ),
            "audio_stream": (summary["has_audio"] if require_audio else True),
        }
    )
    if not all(validation["checks"].values()):
        raise OutputValidationError("render output failed validation", validation)

    validation["status"] = "passed"
    return validation


def summarize_ffprobe(payload: dict) -> dict:
    streams = payload.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    format_payload = payload.get("format") or {}

    return {
        "has_video": bool(video_stream),
        "has_audio": audio_stream is not None,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "duration_seconds": _float_or_zero(format_payload.get("duration") or video_stream.get("duration")),
        "container": format_payload.get("format_name") or "",
        "size_bytes": int(format_payload.get("size") or 0),
    }


def _float_or_zero(value: object) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return 0.0
