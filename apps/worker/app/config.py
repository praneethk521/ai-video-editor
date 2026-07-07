from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class WorkerSettings:
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    max_job_seconds: int = int(os.getenv("MAX_RENDER_JOB_SECONDS", "1800"))
    temp_root: str = os.getenv("VIDEO_TEMP_ROOT", "/tmp/ai-video-editor")
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")


settings = WorkerSettings()

