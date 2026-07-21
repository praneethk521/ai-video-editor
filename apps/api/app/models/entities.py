from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(str, enum.Enum):
    created = "created"
    ingesting = "ingesting"
    analyzed = "analyzed"
    planned = "planned"
    rendering = "rendering"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


class RenderStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class PlanStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TeamMember(Base):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.created)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    media_assets: Mapped[list["MediaAsset"]] = relationship(back_populates="project")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND team_id IS NULL) OR (user_id IS NULL AND team_id IS NOT NULL)",
            name="ck_project_member_user_or_team",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ServiceToken(Base):
    __tablename__ = "service_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    scope: Mapped[str] = mapped_column(String(64), default="worker")
    role: Mapped[str] = mapped_column(String(32), default="worker")
    status: Mapped[str] = mapped_column(String(32), default="active")
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), default="google_drive")
    folder_url_hash: Mapped[str] = mapped_column(String(128))
    selected_folder_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scopes: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending_oauth")
    oauth_state_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    encrypted_token_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(200))
    sanitized_filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    orientation: Mapped[str] = mapped_column(String(32), default="unknown")
    private_locator: Mapped[str] = mapped_column(String(512))
    content_checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    malware_scan_status: Mapped[str] = mapped_column(String(32), default="pending")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="media_assets")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TimelinePlan(Base):
    __tablename__ = "timeline_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    variant: Mapped[str] = mapped_column(String(32))
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), default=PlanStatus.draft)
    confidence_score: Mapped[float] = mapped_column(Float)
    plan_json: Mapped[dict] = mapped_column(JSON)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    timeline_plan_id: Mapped[str] = mapped_column(ForeignKey("timeline_plans.id"), index=True)
    variant: Mapped[str] = mapped_column(String(32))
    status: Mapped[RenderStatus] = mapped_column(Enum(RenderStatus), default=RenderStatus.queued)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OutputVideo(Base):
    __tablename__ = "output_videos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    render_job_id: Mapped[str] = mapped_column(ForeignKey("render_jobs.id"), index=True)
    variant: Mapped[str] = mapped_column(String(32))
    private_locator: Mapped[str] = mapped_column(String(512))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[float] = mapped_column(Float)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    upload_package_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    delivery_target: Mapped[str] = mapped_column(String(32), default="drive")
    delivery_status: Mapped[str] = mapped_column(String(32), default="private_staging")
    delivered_locator: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    delivery_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
