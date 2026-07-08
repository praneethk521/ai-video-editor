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
    expected_caption_count: int = 0,
    delivery_target: str = "drive",
    require_audio: bool = True,
    require_embedded_subtitles: bool = False,
    fail_on_black_frames: bool = False,
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
        "signals": {},
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
    black_frame_signal = detect_black_frames(path)
    subtitle_signal = {
        "expected_caption_count": expected_caption_count,
        "embedded_subtitle_stream": summary["has_subtitles"],
        "embedded_subtitles_required": require_embedded_subtitles,
        "plan_captions_present": expected_caption_count > 0,
    }
    delivery_signal = {
        "target": delivery_target,
        "manual_upload_only": True,
        "status": "private_staging",
    }
    duration_tolerance = max(1.0, expected_duration_seconds * 0.05)
    validation["ffprobe"] = summary
    validation["signals"] = {
        "subtitles": subtitle_signal,
        "black_frames": black_frame_signal,
        "delivery": delivery_signal,
    }
    validation["checks"].update(
        {
            "video_stream": summary["has_video"],
            "resolution": summary["width"] == expected_width and summary["height"] == expected_height,
            "duration": (
                summary["duration_seconds"] > 0
                and abs(summary["duration_seconds"] - expected_duration_seconds) <= duration_tolerance
            ),
            "audio_stream": (summary["has_audio"] if require_audio else True),
            "subtitle_presence": summary["has_subtitles"] if require_embedded_subtitles else True,
            "black_frames": not black_frame_signal["detected"] if fail_on_black_frames else True,
            "delivery_target": delivery_target in {"drive", "s3", "local_private"},
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
    subtitle_stream = next((stream for stream in streams if stream.get("codec_type") == "subtitle"), None)
    format_payload = payload.get("format") or {}

    return {
        "has_video": bool(video_stream),
        "has_audio": audio_stream is not None,
        "has_subtitles": subtitle_stream is not None,
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


def detect_black_frames(path: Path) -> dict:
    command = [
        settings.ffmpeg_path,
        "-hide_banner",
        "-i",
        str(path),
        "-vf",
        "blackdetect=d=0.2:pix_th=0.10",
        "-an",
        "-f",
        "null",
        "-",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=settings.max_job_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "skipped", "detected": False, "reason": str(exc), "segments": []}
    return parse_blackdetect_output(completed.stderr)


def parse_blackdetect_output(stderr: str) -> dict:
    segments = []
    for line in stderr.splitlines():
        if "black_start:" not in line or "black_end:" not in line:
            continue
        segment = {}
        for token in line.split():
            if token.startswith("black_start:"):
                segment["start"] = _float_or_zero(token.split(":", 1)[1])
            elif token.startswith("black_end:"):
                segment["end"] = _float_or_zero(token.split(":", 1)[1])
            elif token.startswith("black_duration:"):
                segment["duration"] = _float_or_zero(token.split(":", 1)[1])
        if segment:
            segments.append(segment)
    return {
        "status": "warning" if segments else "passed",
        "detected": bool(segments),
        "segments": segments,
        "total_duration_seconds": round(sum(segment.get("duration", 0) for segment in segments), 3),
    }
