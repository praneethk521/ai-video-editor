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
    metrics_port: int = int(os.getenv("WORKER_METRICS_PORT", "9100"))
    tracing_enabled: bool = os.getenv("TRACING_ENABLED", "false").lower() in {"1", "true", "yes"}
    otel_service_name: str = os.getenv("OTEL_SERVICE_NAME", "ai-video-editor-worker")
    otel_exporter_otlp_endpoint: str = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces"
    )
    otel_exporter_otlp_headers: str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    otel_trace_sample_ratio: float = float(os.getenv("OTEL_TRACE_SAMPLE_RATIO", "0.1"))

    def __post_init__(self) -> None:
        if not 0 <= self.otel_trace_sample_ratio <= 1:
            raise ValueError("OTEL_TRACE_SAMPLE_RATIO must be between 0 and 1")


settings = WorkerSettings()
