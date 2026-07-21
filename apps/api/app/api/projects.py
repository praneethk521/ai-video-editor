from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.entities import MediaAsset, OutputVideo, Project, ProjectStatus, RenderJob
from app.schemas.api import (
    AnalyzeResponse,
    AnalysisResultsResponse,
    ConnectDriveRequest,
    ConnectDriveResponse,
    DriveSyncResponse,
    IngestRequest,
    IngestResponse,
    OutputResponse,
    OutputRetentionCleanupRequest,
    OutputRetentionCleanupResponse,
    OutputRetentionReportResponse,
    PlanRegenerateRequest,
    PlanReviewRequest,
    ProjectCreate,
    ProjectRead,
    ProjectStatusResponse,
    RenderRequest,
    RenderResponse,
    TimelinePlanRead,
    TimelinePlansResponse,
)
from app.services.audit import audit
from app.services.analysis_providers import AnalysisProviderError
from app.services.authorization import project_role_for_user, role_allows
from app.services.media import complete_drive_oauth, create_drive_connection, create_media_asset, sync_drive_folder
from app.services.output_delivery import cleanup_due_delivered_output
from app.services.planning import (
    analyze_and_plan,
    approve_timeline_plan,
    list_analysis_results,
    list_timeline_plans,
    regenerate_timeline_plans,
    reject_timeline_plan,
)
from app.services.rate_limits import enforce_project_rate_limit
from app.services.rendering import create_render_jobs, dispatch_render_jobs, fail_render_job

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_for_role_or_404(
    db: Session,
    project_id: str,
    user: CurrentUser,
    minimum_role: str,
    request: Request,
    requested_action: str,
) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.status == ProjectStatus.deleted:
        audit_project_authorization(
            db,
            user=user,
            project_id=project_id,
            minimum_role=minimum_role,
            actual_role=None,
            requested_action=requested_action,
            outcome="denied",
            reason="project_not_found",
            correlation_id=request.state.correlation_id,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    actual_role = project_role_for_user(db, project=project, user=user)
    allowed = role_allows(actual_role, minimum_role)
    audit_project_authorization(
        db,
        user=user,
        project_id=project.id,
        minimum_role=minimum_role,
        actual_role=actual_role,
        requested_action=requested_action,
        outcome="allowed" if allowed else "denied",
        reason=None if allowed else "insufficient_project_role",
        correlation_id=request.state.correlation_id,
    )
    db.commit()
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient project role")
    return project


def audit_project_authorization(
    db: Session,
    *,
    user: CurrentUser,
    project_id: str,
    minimum_role: str,
    actual_role: str | None,
    requested_action: str,
    outcome: str,
    reason: str | None,
    correlation_id: str,
) -> None:
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="authorization.project",
        correlation_id=correlation_id,
        metadata={
            "requested_action": requested_action,
            "minimum_role": minimum_role,
            "actual_role": actual_role,
            "outcome": outcome,
            "reason": reason,
        },
    )


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
    get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="drive.connection.create"
    )
    connection, authorization_url = create_drive_connection(db, project_id=project_id, folder_url=str(payload.folder_url))
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
    return ConnectDriveResponse(
        connection_id=connection.id,
        status=connection.status,
        scopes=connection.scopes,
        authorization_url=authorization_url,
    )


@router.get("/{project_id}/connect-drive/callback", response_model=ConnectDriveResponse)
def connect_drive_callback(
    project_id: str,
    code: str,
    state: str,
    request: Request,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if project is None or project.status == ProjectStatus.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    try:
        connection = complete_drive_oauth(db, project_id=project_id, state=state, code=code)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id="oauth-callback",
        project_id=project_id,
        action="drive.oauth.connected",
        correlation_id=request.state.correlation_id,
        metadata={"scopes": connection.scopes, "provider": connection.provider},
    )
    db.commit()
    return ConnectDriveResponse(connection_id=connection.id, status=connection.status, scopes=connection.scopes)


@router.post("/{project_id}/ingest", response_model=IngestResponse)
def ingest(
    project_id: str,
    payload: IngestRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="media.ingest"
    )
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


@router.post("/{project_id}/sync-drive", response_model=DriveSyncResponse)
def sync_drive(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="drive.folder.sync"
    )
    enforce_project_rate_limit(request, project_id=project.id, action="drive.folder.sync")
    try:
        result = sync_drive_folder(db, project_id=project.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    project.status = ProjectStatus.ingesting
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="drive.folder.synced",
        correlation_id=request.state.correlation_id,
        metadata={
            "discovered_count": result["discovered_count"],
            "accepted_count": len(result["accepted_asset_ids"]),
            "duplicate_count": result["duplicate_count"],
            "skipped_count": result["skipped_count"],
        },
    )
    db.commit()
    return DriveSyncResponse(**result)


@router.post("/{project_id}/analyze", response_model=AnalyzeResponse)
def analyze(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="project.analyze"
    )
    enforce_project_rate_limit(request, project_id=project.id, action="project.analyze")
    try:
        analysis, plans = analyze_and_plan(db, project_id=project.id)
    except AnalysisProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "details": exc.details},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    project.status = ProjectStatus.planned
    audit(db, user_id=user.id, project_id=project_id, action="project.analyzed", correlation_id=request.state.correlation_id)
    db.commit()
    return AnalyzeResponse(analysis_id=analysis.id, timeline_plan_ids=[plan.id for plan in plans])


@router.get("/{project_id}/analysis", response_model=AnalysisResultsResponse)
def analysis_results(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="viewer", request=request, requested_action="analysis.results.read"
    )
    return AnalysisResultsResponse(
        results=[
            {
                "id": result.id,
                "provider": result.provider,
                "created_at": result.created_at.isoformat(),
                "result": result.result_json,
            }
            for result in list_analysis_results(db, project_id=project.id)
        ]
    )


@router.get("/{project_id}/plans", response_model=TimelinePlansResponse)
def timeline_plans(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="viewer", request=request, requested_action="timeline.plans.read"
    )
    return TimelinePlansResponse(plans=[plan_to_response(plan) for plan in list_timeline_plans(db, project_id=project.id)])


@router.post("/{project_id}/plans/regenerate", response_model=AnalyzeResponse)
def regenerate_plans(
    project_id: str,
    payload: PlanRegenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="timeline.plans.regenerate"
    )
    enforce_project_rate_limit(request, project_id=project.id, action="timeline.plans.regenerate")
    try:
        plans = regenerate_timeline_plans(db, project_id=project.id, variants=payload.variants, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="timeline.plans.regenerated",
        correlation_id=request.state.correlation_id,
        metadata={"variants": payload.variants},
    )
    db.commit()
    return AnalyzeResponse(analysis_id="", timeline_plan_ids=[plan.id for plan in plans])


@router.post("/{project_id}/plans/{plan_id}/approve", response_model=TimelinePlanRead)
def approve_plan(
    project_id: str,
    plan_id: str,
    payload: PlanReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    get_project_for_role_or_404(
        db, project_id, user, minimum_role="reviewer", request=request, requested_action="timeline.plan.approve"
    )
    try:
        plan = approve_timeline_plan(db, project_id=project_id, plan_id=plan_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="timeline.plan.approved",
        correlation_id=request.state.correlation_id,
        metadata={"plan_id": plan_id, "variant": plan.variant},
    )
    db.commit()
    return plan_to_response(plan)


@router.post("/{project_id}/plans/{plan_id}/reject", response_model=TimelinePlanRead)
def reject_plan(
    project_id: str,
    plan_id: str,
    payload: PlanReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    get_project_for_role_or_404(
        db, project_id, user, minimum_role="reviewer", request=request, requested_action="timeline.plan.reject"
    )
    try:
        plan = reject_timeline_plan(db, project_id=project_id, plan_id=plan_id, notes=payload.notes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="timeline.plan.rejected",
        correlation_id=request.state.correlation_id,
        metadata={"plan_id": plan_id, "variant": plan.variant},
    )
    db.commit()
    return plan_to_response(plan)


@router.post("/{project_id}/render", response_model=RenderResponse)
def render(
    project_id: str,
    payload: RenderRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="render.jobs.queue"
    )
    enforce_project_rate_limit(request, project_id=project.id, action="render.jobs.queue")
    try:
        jobs, queue_items = create_render_jobs(db, project_id=project.id, variants=payload.variants)
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
    try:
        dispatch_render_jobs(queue_items)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        for job in jobs:
            fail_render_job(db, render_job_id=job.id, error_message=f"failed to enqueue render job: {exc}")
        audit(
            db,
            user_id=user.id,
            project_id=project_id,
            action="render.jobs.enqueue_failed",
            correlation_id=request.state.correlation_id,
            metadata={"job_count": len(jobs)},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="render queue unavailable") from exc
    return RenderResponse(render_job_ids=[job.id for job in jobs])


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
def project_status(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="viewer", request=request, requested_action="project.status.read"
    )
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
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="viewer", request=request, requested_action="outputs.read"
    )
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
                "validation": row.validation_json,
                "delivery": {
                    "target": row.delivery_target,
                    "status": row.delivery_status,
                    "delivered_locator": row.delivered_locator,
                    "details": row.delivery_json,
                },
            }
            for row in rows
        ]
    )


@router.get("/{project_id}/outputs/retention", response_model=OutputRetentionReportResponse)
def output_retention_report(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="viewer", request=request, requested_action="outputs.retention.read"
    )
    rows = db.query(OutputVideo).filter(OutputVideo.project_id == project.id).all()
    return OutputRetentionReportResponse(
        project_id=project.id,
        outputs=[output_retention_row(row) for row in rows],
    )


@router.post("/{project_id}/outputs/retention/cleanup", response_model=OutputRetentionCleanupResponse)
def cleanup_due_output_retention(
    project_id: str,
    payload: OutputRetentionCleanupRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    minimum_role = "operator" if payload.dry_run else "owner"
    project = get_project_for_role_or_404(
        db,
        project_id,
        user,
        minimum_role=minimum_role,
        request=request,
        requested_action="outputs.retention.cleanup_preview" if payload.dry_run else "outputs.retention.cleanup_execute",
    )
    enforce_project_rate_limit(
        request,
        project_id=project.id,
        action="outputs.retention.cleanup_preview" if payload.dry_run else "outputs.retention.cleanup_execute",
    )
    rows = db.query(OutputVideo).filter(OutputVideo.project_id == project.id).all()
    results = [cleanup_due_delivered_output(row, dry_run=payload.dry_run) for row in rows]
    audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="output.retention.cleanup_reviewed" if payload.dry_run else "output.retention.cleanup_completed",
        correlation_id=request.state.correlation_id,
        metadata={
            "dry_run": payload.dry_run,
            "output_count": len(results),
            "deleted_count": len([row for row in results if row["cleanup"]["status"] == "deleted"]),
            "would_delete_count": len([row for row in results if row["cleanup"]["status"] == "would_delete"]),
        },
    )
    db.commit()
    return OutputRetentionCleanupResponse(project_id=project.id, dry_run=payload.dry_run, outputs=results)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="owner", request=request, requested_action="project.delete"
    )
    project.status = ProjectStatus.deleted
    audit(db, user_id=user.id, project_id=project_id, action="project.deleted", correlation_id=request.state.correlation_id)
    db.commit()
    return None


def output_retention_row(row: OutputVideo) -> dict:
    delivery_json = row.delivery_json or {}
    details = delivery_json.get("details") or {}
    retention = details.get("retention") or {}
    cleanup = delivery_json.get("staged_source_cleanup") or {}
    delivered_cleanup = delivery_json.get("delivered_artifact_cleanup") or {}
    days_until_delete = days_until_retention_delete(retention.get("delete_after"))
    return {
        "id": row.id,
        "variant": row.variant,
        "target": row.delivery_target,
        "status": row.delivery_status,
        "delivered_locator": row.delivered_locator,
        "has_retention_metadata": bool(retention),
        "retention": retention,
        "cleanup_status": cleanup.get("status"),
        "delivered_artifact_cleanup_status": delivered_cleanup.get("status"),
        "days_until_delete": days_until_delete,
        "retention_due": days_until_delete is not None and days_until_delete <= 0,
    }


def days_until_retention_delete(delete_after: object) -> int | None:
    if not isinstance(delete_after, str):
        return None
    try:
        return (date.fromisoformat(delete_after) - date.today()).days
    except ValueError:
        return None


def plan_to_response(plan) -> TimelinePlanRead:
    return TimelinePlanRead(
        id=plan.id,
        variant=plan.variant,
        status=plan.status.value,
        confidence_score=plan.confidence_score,
        plan=plan.plan_json,
        review_notes=plan.review_notes,
    )
