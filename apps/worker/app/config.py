from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class WorkerSettings:
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    api_token: str = os.getenv("API_TOKEN", "dev-only-token")
    max_job_seconds: int = int(os.getenv("MAX_RENDER_JOB_SECONDS", "1800"))
    temp_root: str = os.getenv("VIDEO_TEMP_ROOT", "/tmp/ai-video-editor")
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")
    ffprobe_path: str = os.getenv("FFPROBE_PATH", "ffprobe")
    output_storage_provider: str = os.getenv("OUTPUT_STORAGE_PROVIDER", "drive")
    require_embedded_subtitles: bool = os.getenv("REQUIRE_EMBEDDED_SUBTITLES", "false").lower() in {"1", "true", "yes"}
    fail_on_black_frames: bool = os.getenv("FAIL_ON_BLACK_FRAMES", "false").lower() in {"1", "true", "yes"}
    render_dry_run: bool = os.getenv("RENDER_DRY_RUN", "true").lower() in {"1", "true", "yes"}


settings = WorkerSettings()
