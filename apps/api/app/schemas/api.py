from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str


class CurrentUserRead(BaseModel):
    id: str
    email: str
    role: str


MembershipRole = Literal["viewer", "reviewer", "operator", "owner"]


class MembershipRoleUpdate(BaseModel):
    role: MembershipRole


class UserMembershipRoleUpdate(MembershipRoleUpdate):
    email: str = Field(min_length=3, max_length=255)


class ProjectMembershipRead(BaseModel):
    id: str
    principal_type: Literal["user", "team"]
    principal_id: str
    principal_name: str
    role: MembershipRole


class ProjectMembershipsResponse(BaseModel):
    members: list[ProjectMembershipRead]


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class TeamRead(BaseModel):
    id: str
    name: str
    role: str


class TeamsResponse(BaseModel):
    teams: list[TeamRead]


class TeamMemberRead(BaseModel):
    id: str
    user_id: str
    email: str
    role: MembershipRole


class TeamMembersResponse(BaseModel):
    members: list[TeamMemberRead]


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


class MediaAssetRead(BaseModel):
    id: str
    filename: str
    mime_type: str
    duration_seconds: float
    orientation: str


class MediaAssetsResponse(BaseModel):
    media: list[MediaAssetRead]


class PlanDecisionUpdate(BaseModel):
    asset_id: str = Field(min_length=1, max_length=64)
    selected: bool
    pinned: bool = False
    start: float = Field(default=0, ge=0)
    duration: float = Field(default=3, gt=0, le=8)


class PlanUpdateRequest(BaseModel):
    decisions: list[PlanDecisionUpdate] = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class PlanReviewRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class SoundtrackUpdateRequest(BaseModel):
    mode: Literal["auto", "latest", "manual", "none"]
    asset_id: str | None = Field(default=None, min_length=1, max_length=64)


class PlanRegenerateRequest(BaseModel):
    variants: list[str] = Field(default_factory=lambda: ["youtube_16x9", "shorts_9x16"])
    notes: str | None = Field(default=None, max_length=2000)
    landscape_target_seconds: int | None = Field(default=None, ge=15, le=300)
    portrait_target_seconds: int | None = Field(default=None, ge=15, le=60)


class RenderRequest(BaseModel):
    variants: list[str] = Field(default_factory=lambda: ["youtube_16x9", "shorts_9x16"])


class RenderResponse(BaseModel):
    render_job_ids: list[str]


class ProjectStatusResponse(BaseModel):
    project_id: str
    status: str
    role: str
    media_count: int
    render_jobs: list[dict]
    pipeline: dict


class ProjectUsageMetric(BaseModel):
    metric: str
    label: str
    unit: str
    used: int
    limit: int
    remaining: int


class ProjectUsageResponse(BaseModel):
    project_id: str
    window_start: datetime
    window_end: datetime
    metrics: list[ProjectUsageMetric]
    active_delivered_storage_bytes: int
    active_delivered_output_count: int


class OutputResponse(BaseModel):
    outputs: list[dict]


class OutputRetentionReportResponse(BaseModel):
    project_id: str
    outputs: list[dict]


class OutputRetentionCleanupRequest(BaseModel):
    dry_run: bool = True


class OutputRetentionCleanupResponse(BaseModel):
    project_id: str
    dry_run: bool
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
