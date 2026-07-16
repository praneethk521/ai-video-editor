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
    authorization_url: str | None = None


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


class DriveSyncResponse(BaseModel):
    discovered_count: int
    accepted_asset_ids: list[str]
    duplicate_count: int
    skipped_count: int


class AnalyzeResponse(BaseModel):
    analysis_id: str
    timeline_plan_ids: list[str]


class AnalysisResultsResponse(BaseModel):
    results: list[dict]


class TimelinePlanRead(BaseModel):
    id: str
    variant: str
    status: str
    confidence_score: float
    plan: dict
    review_notes: str | None = None


class TimelinePlansResponse(BaseModel):
    plans: list[TimelinePlanRead]


class PlanReviewRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class PlanRegenerateRequest(BaseModel):
    variants: list[str] = Field(default_factory=lambda: ["youtube_16x9", "shorts_9x16"])
    notes: str | None = Field(default=None, max_length=2000)


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


class OutputRetentionReportResponse(BaseModel):
    project_id: str
    outputs: list[dict]


class WorkerRenderCompleteRequest(BaseModel):
    variant: str
    private_locator: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_seconds: float = Field(ge=0)
    file_size_bytes: int = Field(ge=0)
    upload_package: dict
    validation: dict = Field(default_factory=dict)


class WorkerRenderFailedRequest(BaseModel):
    error_message: str = Field(min_length=1, max_length=2000)


class OutputDeliveryRequest(BaseModel):
    target: str = Field(min_length=1, max_length=32)
    status: str = Field(min_length=1, max_length=64)
    delivered_locator: str | None = Field(default=None, max_length=512)
    details: dict = Field(default_factory=dict)


class OutputDeliverRequest(BaseModel):
    target: str | None = Field(default=None, max_length=32)


class MalwareScanResultRequest(BaseModel):
    status: str
    scanner: str = Field(default="manual")
    details: dict = Field(default_factory=dict)
