from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.entities import MediaAsset, OutputVideo, Project, ProjectStatus, RenderJob
from app.schemas.api import (
    AnalyzeResponse,
    ConnectDriveRequest,
    ConnectDriveResponse,
    IngestRequest,
    IngestResponse,
    OutputResponse,
    ProjectCreate,
    ProjectRead,
    ProjectStatusResponse,
    RenderRequest,
    RenderResponse,
)
from app.services.audit import audit
from app.services.media import create_drive_connection, create_media_asset
from app.services.planning import analyze_and_plan
from app.services.rendering import enqueue_render_jobs

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_or_404(db: Session, project_id: str, user: CurrentUser) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_user_id != user.id or project.status == ProjectStatus.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = Project(name=payload.name, owner_user_id=user.id)
    db.add(project)
    db.flush()
    audit(db, user_id=user.id, project_id=project.id, action="project.created", correlation_id=request.state.correlation_id)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/connect-drive", response_model=ConnectDriveResponse)
def connect_drive(
    project_id: str,
    payload: ConnectDriveRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    get_project_or_404(db, project_id, user)
    connection = create_drive_connection(db, project_id=project_id, folder_url=str(payload.folder_url))
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="drive.connection.created",
        correlation_id=request.state.correlation_id,
        metadata={"folder_url": str(payload.folder_url), "scopes": connection.scopes},
    )
    db.commit()
    db.refresh(connection)
    return ConnectDriveResponse(connection_id=connection.id, status=connection.status, scopes=connection.scopes)


@router.post("/{project_id}/ingest", response_model=IngestResponse)
def ingest(
    project_id: str,
    payload: IngestRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id, user)
    accepted = []
    try:
        for asset in payload.assets:
            media = create_media_asset(db, project_id=project.id, asset=asset)
            db.flush()
            accepted.append(media.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    project.status = ProjectStatus.ingesting
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="media.ingested",
        correlation_id=request.state.correlation_id,
        metadata={"asset_count": len(accepted)},
    )
    db.commit()
    return IngestResponse(accepted_asset_ids=accepted)


@router.post("/{project_id}/analyze", response_model=AnalyzeResponse)
def analyze(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id, user)
    try:
        analysis, plans = analyze_and_plan(db, project_id=project.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    project.status = ProjectStatus.planned
    audit(db, user_id=user.id, project_id=project_id, action="project.analyzed", correlation_id=request.state.correlation_id)
    db.commit()
    return AnalyzeResponse(analysis_id=analysis.id, timeline_plan_ids=[plan.id for plan in plans])


@router.post("/{project_id}/render", response_model=RenderResponse)
def render(
    project_id: str,
    payload: RenderRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id, user)
    try:
        jobs = enqueue_render_jobs(db, project_id=project.id, variants=payload.variants)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    project.status = ProjectStatus.rendering
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="render.jobs.queued",
        correlation_id=request.state.correlation_id,
        metadata={"job_count": len(jobs)},
    )
    db.commit()
    return RenderResponse(render_job_ids=[job.id for job in jobs])


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
def project_status(
    project_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id, user)
    jobs = db.query(RenderJob).filter(RenderJob.project_id == project.id).all()
    media_count = db.query(MediaAsset).filter(MediaAsset.project_id == project.id).count()
    return ProjectStatusResponse(
        project_id=project.id,
        status=project.status.value,
        media_count=media_count,
        render_jobs=[{"id": job.id, "variant": job.variant, "status": job.status.value} for job in jobs],
    )


@router.get("/{project_id}/outputs", response_model=OutputResponse)
def outputs(
    project_id: str,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id, user)
    rows = db.query(OutputVideo).filter(OutputVideo.project_id == project.id).all()
    return OutputResponse(
        outputs=[
            {
                "id": row.id,
                "variant": row.variant,
                "width": row.width,
                "height": row.height,
                "duration_seconds": row.duration_seconds,
                "private_locator": row.private_locator,
                "upload_package": row.upload_package_json,
            }
            for row in rows
        ]
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id, user)
    project.status = ProjectStatus.deleted
    audit(db, user_id=user.id, project_id=project_id, action="project.deleted", correlation_id=request.state.correlation_id)
    db.commit()
    return None

