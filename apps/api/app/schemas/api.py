from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str


class ConnectDriveRequest(BaseModel):
    folder_url: HttpUrl


class ConnectDriveResponse(BaseModel):
    connection_id: str
    status: str
    scopes: str


class IngestAsset(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int = Field(gt=0)
    duration_seconds: float = Field(default=0, ge=0)
    orientation: str = "unknown"
    private_locator: str


class IngestRequest(BaseModel):
    assets: list[IngestAsset] = Field(min_length=1, max_length=500)


class IngestResponse(BaseModel):
    accepted_asset_ids: list[str]


class AnalyzeResponse(BaseModel):
    analysis_id: str
    timeline_plan_ids: list[str]


class RenderRequest(BaseModel):
    variants: list[str] = Field(default_factory=lambda: ["youtube_16x9", "shorts_9x16"])


class RenderResponse(BaseModel):
    render_job_ids: list[str]


class ProjectStatusResponse(BaseModel):
    project_id: str
    status: str
    media_count: int
    render_jobs: list[dict]


class OutputResponse(BaseModel):
    outputs: list[dict]

