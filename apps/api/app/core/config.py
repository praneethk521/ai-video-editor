from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    api_token: str = Field(default="dev-only-token", repr=False)
    user_auth_mode: Literal["local_bearer", "oidc"] = "local_bearer"
    legacy_service_token_enabled: bool = True
    oidc_issuer_url: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_algorithms: str = "RS256"
    oidc_subject_claim: str = "sub"
    oidc_email_claim: str = "email"
    oidc_role_claim: str = "role"
    oidc_admin_role: str = "admin"
    oidc_leeway_seconds: int = Field(default=30, ge=0, le=300)
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:3001"
    trusted_hosts: str = "localhost,127.0.0.1,testserver,api"
    database_url: str = "sqlite+pysqlite:///./local.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    render_queue_backend: str = "rq"
    render_job_timeout_seconds: int = 1800
    rate_limits_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_redis_prefix: str = "ai-video-editor:rate-limit"
    expensive_workflow_rate_limit_per_minute: int = 20
    render_rate_limit_per_minute: int = 10
    retention_cleanup_rate_limit_per_minute: int = 6
    quota_enforcement_enabled: bool = True
    analysis_requests_per_project_per_day: int = 50
    render_jobs_per_project_per_day: int = 40
    delivered_storage_bytes_per_project_per_day: int = 10_737_418_240
    delivery_attempts_per_project_per_day: int = 40
    provider_cost_cents_per_project_per_day: int = 2_500
    analysis_provider_estimated_cost_cents_per_request: int = 0
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    otel_service_name: str = "ai-video-editor-api"
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4318/v1/traces"
    otel_exporter_otlp_headers: str = Field(default="", repr=False)
    otel_trace_sample_ratio: float = Field(default=0.1, ge=0, le=1)
    google_client_id: str = ""
    google_client_secret: str = Field(default="", repr=False)
    google_photos_redirect_uri: str = "http://localhost:8001/oauth/google-photos/callback"
    google_oauth_redirect_uri: str = "http://localhost:8000/projects/{project_id}/connect-drive/callback"
    google_oauth_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_oauth_token_url: str = "https://oauth2.googleapis.com/token"
    google_drive_files_url: str = "https://www.googleapis.com/drive/v3/files"
    google_drive_upload_url: str = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
    google_drive_download_url: str = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    google_drive_output_folder_id: str = ""
    google_drive_scopes: str = "https://www.googleapis.com/auth/drive.readonly"
    token_encryption_key: str = Field(default="", repr=False)
    malware_scanner_backend: str = "clamav"
    analysis_provider: str = "deterministic_local"
    analysis_provider_url: str = ""
    analysis_provider_health_url: str = ""
    analysis_provider_token: str = Field(default="", repr=False)
    analysis_provider_timeout_seconds: int = 60
    analysis_provider_max_attempts: int = 2
    analysis_provider_retry_backoff_seconds: float = 0.25
    analysis_provider_circuit_failure_threshold: int = 3
    analysis_provider_circuit_reset_seconds: int = 60
    analysis_provider_include_private_locator: bool = False
    local_vision_enabled: bool = False
    local_vision_url: str = "http://127.0.0.1:11434"
    local_vision_model: str = "qwen2.5vl:7b"
    local_vision_timeout_seconds: int = Field(default=120, ge=10, le=600)
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    max_upload_bytes: int = 2_147_483_648
    media_source_root: str = "/tmp/ai-video-editor/sources"
    ffprobe_path: str = "ffprobe"
    ffmpeg_path: str = "ffmpeg"
    max_project_media: int = Field(default=500, ge=1, le=500)
    landscape_target_seconds: int = Field(default=90, ge=15, le=300)
    portrait_target_seconds: int = Field(default=30, ge=15, le=60)
    allowed_media_mimes: set[str] = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "video/mp4",
        "video/quicktime",
        "video/webm",
        "audio/mpeg",
        "audio/wav",
    }
    output_storage_provider: str = "drive"
    auto_deliver_outputs: bool = False
    cleanup_staged_outputs_after_delivery: bool = False
    delivered_output_retention_days: int = 30
    delivered_output_retention_policy: str = "manual_upload_private_output"
    output_delivery_local_root: str = "/tmp/ai-video-editor/outputs"
    local_private_delivery_root: str = "/tmp/ai-video-editor/delivered"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_prefix: str = "ai-video-editor/outputs"
    media_encryption_kms_key_id: str = ""


def validate_auth_configuration(value: Settings) -> None:
    if value.user_auth_mode == "oidc":
        missing = [
            name
            for name, configured in {
                "OIDC_ISSUER_URL": value.oidc_issuer_url,
                "OIDC_AUDIENCE": value.oidc_audience,
                "OIDC_JWKS_URL": value.oidc_jwks_url,
            }.items()
            if not configured.strip()
        ]
        if missing:
            raise RuntimeError(f"OIDC authentication requires: {', '.join(missing)}")
        algorithms = {algorithm.strip() for algorithm in value.oidc_algorithms.split(",") if algorithm.strip()}
        allowed_algorithms = {"ES256", "ES384", "ES512", "PS256", "PS384", "PS512", "RS256", "RS384", "RS512"}
        if not algorithms or algorithms - allowed_algorithms:
            raise RuntimeError("OIDC_ALGORITHMS must contain only approved asymmetric algorithms")
    if value.app_env.lower() == "production":
        if value.user_auth_mode != "oidc":
            raise RuntimeError("production requires USER_AUTH_MODE=oidc")
        if value.legacy_service_token_enabled:
            raise RuntimeError("production requires LEGACY_SERVICE_TOKEN_ENABLED=false")
        if not value.oidc_issuer_url.startswith("https://") or not value.oidc_jwks_url.startswith("https://"):
            raise RuntimeError("production OIDC issuer and JWKS URLs must use HTTPS")
        origins = comma_separated_values(value.cors_allowed_origins)
        if not origins or any(not origin.startswith("https://") for origin in origins):
            raise RuntimeError("production CORS_ALLOWED_ORIGINS must contain explicit HTTPS origins")
        hosts = comma_separated_values(value.trusted_hosts)
        if not hosts or "*" in hosts:
            raise RuntimeError("production TRUSTED_HOSTS must contain explicit hosts")


def comma_separated_values(raw_value: str) -> list[str]:
    return [value.strip() for value in raw_value.split(",") if value.strip()]


settings = Settings()
