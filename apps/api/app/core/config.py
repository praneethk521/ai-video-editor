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
    google_client_id: str = ""
    google_client_secret: str = Field(default="", repr=False)
    google_oauth_redirect_uri: str = "http://localhost:8000/projects/{project_id}/connect-drive/callback"
    google_oauth_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_oauth_token_url: str = "https://oauth2.googleapis.com/token"
    google_drive_files_url: str = "https://www.googleapis.com/drive/v3/files"
    google_drive_download_url: str = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    google_drive_scopes: str = "https://www.googleapis.com/auth/drive.readonly"
    token_encryption_key: str = Field(default="", repr=False)
    malware_scanner_backend: str = "clamav"
    analysis_provider: str = "deterministic_local"
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


settings = Settings()
