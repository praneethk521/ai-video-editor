from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    api_token: str = Field(default="dev-only-token", repr=False)
    database_url: str = "sqlite+pysqlite:///./local.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    render_queue_backend: str = "rq"
    render_job_timeout_seconds: int = 1800
    rate_limits_enabled: bool = True
    expensive_workflow_rate_limit_per_minute: int = 20
    render_rate_limit_per_minute: int = 10
    retention_cleanup_rate_limit_per_minute: int = 6
    google_client_id: str = ""
    google_client_secret: str = Field(default="", repr=False)
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
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    max_upload_bytes: int = 2_147_483_648
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


settings = Settings()
