from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    api_token: str = Field(default="dev-only-token", repr=False)
    database_url: str = "sqlite+pysqlite:///./local.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    google_drive_scopes: str = "https://www.googleapis.com/auth/drive.readonly"
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

