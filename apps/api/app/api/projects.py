from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import CurrentUser, get_current_human_user, get_current_user
from app.db.session import get_db
from app.models.entities import MediaAsset, OutputVideo, Project, ProjectMember, ProjectStatus, RenderJob, Team, User
from app.schemas.api import (
    AnalyzeResponse,
    AnalysisResultsResponse,
    ConnectDriveRequest,
    ConnectDriveResponse,
    DriveSyncResponse,
    IngestRequest,
    IngestResponse,
    MediaAssetRead,
    MediaAssetsResponse,
    OutputResponse,
    OutputDeliverRequest,
    OutputRetentionCleanupRequest,
    OutputRetentionCleanupResponse,
    OutputRetentionReportResponse,
    PlanRegenerateRequest,
    PlanReviewRequest,
    PlanUpdateRequest,
    MembershipRoleUpdate,
    ProjectCreate,
    ProjectMembershipRead,
    ProjectMembershipsResponse,
    ProjectRead,
    ProjectStatusResponse,
    ProjectUsageResponse,
    RenderRequest,
    RenderResponse,
    SoundtrackUpdateRequest,
    TimelinePlanRead,
    TimelinePlansResponse,
    UserMembershipRoleUpdate,
)
from app.services.audit import audit
from app.services.analysis_providers import AnalysisProviderError
from app.services.authorization import project_role_for_user, role_allows
from app.services.media import complete_drive_oauth, create_drive_connection, create_media_asset, sync_drive_folder
from app.services.local_media import media_thumbnail, upload_local_media
from app.services.metrics import record_workflow_event
from app.services.output_delivery import cleanup_due_delivered_output, deliver_output_video, record_output_delivery_failure, resolve_private_file_locator
from app.services.planning import (
    analyze_and_plan,
    approve_timeline_plan,
    list_analysis_results,
    list_timeline_plans,
    regenerate_timeline_plans,
    reject_timeline_plan,
    set_plan_soundtrack,
    update_timeline_plan,
)
from app.services.quotas import (
    ANALYSIS_REQUESTS,
    PROVIDER_COST_CENTS,
    RENDER_JOBS,
    consume_project_quota,
    project_usage_summary,
)
from app.services.project_progress import derive_project_pipeline
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
    user: CurrentUser = Depends(get_current_human_user),
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


@router.post("/{project_id}/upload", response_model=IngestResponse, status_code=201)
def upload_media(project_id: str, request: Request, file: UploadFile,
                 db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    project = get_project_for_role_or_404(db, project_id, user, "operator", request, "media.upload")
    enforce_project_rate_limit(request, project_id=project.id, action="media.upload")
    try:
        media = upload_local_media(db, project_id=project_id, upload=file)
        project.status = ProjectStatus.ingesting
        audit(db, user_id=user.id, project_id=project_id, action="media.uploaded",
              correlation_id=request.state.correlation_id, metadata={"asset_id": media.id})
        db.commit()
        return IngestResponse(accepted_asset_ids=[media.id])
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        file.file.close()


@router.get("/{project_id}/media", response_model=MediaAssetsResponse)
def list_media(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    get_project_for_role_or_404(db, project_id, user, "viewer", request, "media.list")
    rows = (
        db.query(MediaAsset)
        .filter(MediaAsset.project_id == project_id)
        .order_by(MediaAsset.created_at, MediaAsset.id)
        .all()
    )
    return MediaAssetsResponse(media=[MediaAssetRead(
        id=row.id,
        filename=row.original_filename,
        mime_type=row.mime_type,
        duration_seconds=row.duration_seconds,
        orientation=row.orientation,
    ) for row in rows])


@router.get("/{project_id}/media/{asset_id}/thumbnail")
def get_media_thumbnail(
    project_id: str,
    asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    get_project_for_role_or_404(db, project_id, user, "viewer", request, "media.thumbnail.read")
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.project_id != project_id or asset.malware_scan_status != "clean":
        raise HTTPException(status_code=404, detail="clean media asset not found")
    try:
        thumbnail = media_thumbnail(asset)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=thumbnail, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})


@router.get("/{project_id}/outputs/{output_id}/download")
def download_output(project_id: str, output_id: str, request: Request,
                    db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    get_project_for_role_or_404(db, project_id, user, "viewer", request, "output.download")
    output = db.get(OutputVideo, output_id)
    if output is None or output.project_id != project_id or (output.validation_json or {}).get("status") != "passed":
        raise HTTPException(status_code=404, detail="validated output not found")
    try:
        if not output.private_locator.startswith(f"file://private/{project_id}/"):
            raise ValueError("output belongs to a different project")
        path = resolve_private_file_locator(output.private_locator)
        if not path.is_file():
            raise ValueError("output missing")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="staged output unavailable") from exc
    return FileResponse(path, media_type="video/mp4", filename=f"{output.variant}.mp4")


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
        record_workflow_event("drive_oauth", "failed")
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
    record_workflow_event("drive_oauth", "succeeded")
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
        record_workflow_event("ingest", "failed")
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
    record_workflow_event("ingest", "succeeded")
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
        record_workflow_event("drive_sync", "failed")
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
    record_workflow_event("drive_sync", "succeeded")
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
    consume_project_quota(db, project_id=project.id, metric=ANALYSIS_REQUESTS)
    estimated_provider_cost = settings.analysis_provider_estimated_cost_cents_per_request
    consume_project_quota(
        db,
        project_id=project.id,
        metric=PROVIDER_COST_CENTS,
        amount=estimated_provider_cost,
    )
    db.commit()
    try:
        analysis, plans = analyze_and_plan(db, project_id=project.id)
    except AnalysisProviderError as exc:
        record_workflow_event("analysis", "failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "details": exc.details},
        ) from exc
    except ValueError as exc:
        record_workflow_event("analysis", "failed")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    project.status = ProjectStatus.planned
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="project.analyzed",
        correlation_id=request.state.correlation_id,
        metadata={"provider_cost_cents_estimate": estimated_provider_cost},
    )
    db.commit()
    record_workflow_event("analysis", "succeeded")
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
        plans = regenerate_timeline_plans(db, project_id=project.id, variants=payload.variants, notes=payload.notes,
                                         targets={"youtube_16x9": payload.landscape_target_seconds,
                                                  "shorts_9x16": payload.portrait_target_seconds})
    except ValueError as exc:
        record_workflow_event("plan_regeneration", "failed")
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
    record_workflow_event("plan_regeneration", "succeeded")
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


@router.patch("/{project_id}/plans/{plan_id}", response_model=TimelinePlanRead)
def update_plan(
    project_id: str,
    plan_id: str,
    payload: PlanUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    get_project_for_role_or_404(
        db, project_id, user, minimum_role="reviewer", request=request, requested_action="timeline.plan.update"
    )
    try:
        plan = update_timeline_plan(
            db,
            project_id=project_id,
            plan_id=plan_id,
            decisions=[item.model_dump() for item in payload.decisions],
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="timeline.plan.updated",
        correlation_id=request.state.correlation_id,
        metadata={
            "plan_id": plan_id,
            "variant": plan.variant,
            "selected_count": sum(item.selected or item.pinned for item in payload.decisions),
        },
    )
    db.commit()
    db.refresh(plan)
    return plan_to_response(plan)


@router.put("/{project_id}/plans/{plan_id}/soundtrack", response_model=TimelinePlanRead)
def update_plan_soundtrack(
    project_id: str,
    plan_id: str,
    payload: SoundtrackUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    get_project_for_role_or_404(
        db, project_id, user, minimum_role="reviewer", request=request,
        requested_action="timeline.plan.soundtrack.update",
    )
    try:
        plan = set_plan_soundtrack(
            db,
            project_id=project_id,
            plan_id=plan_id,
            mode=payload.mode,
            asset_id=payload.asset_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=project_id,
        action="timeline.plan.soundtrack.updated",
        correlation_id=request.state.correlation_id,
        metadata={"plan_id": plan_id, "variant": plan.variant, "mode": payload.mode},
    )
    db.commit()
    db.refresh(plan)
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
    consume_project_quota(db, project_id=project.id, metric=RENDER_JOBS, amount=len(payload.variants))
    db.commit()
    try:
        jobs, queue_items = create_render_jobs(db, project_id=project.id, variants=payload.variants)
    except ValueError as exc:
        record_workflow_event("render_queue", "rejected")
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
        record_workflow_event("render_queue", "failed")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        record_workflow_event("render_queue", "failed")
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
    record_workflow_event("render_queue", "queued")
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
        role=project_role_for_user(db, project=project, user=user) or "viewer",
        media_count=media_count,
        render_jobs=[{"id": job.id, "variant": job.variant, "status": job.status.value} for job in jobs],
        pipeline=derive_project_pipeline(db, project_id=project.id),
    )


@router.post("/{project_id}/outputs/{output_video_id}/deliver", status_code=status.HTTP_204_NO_CONTENT)
def deliver_project_output(
    project_id: str,
    output_video_id: str,
    payload: OutputDeliverRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="output.delivery.execute"
    )
    output = db.get(OutputVideo, output_video_id)
    if output is None or output.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="output video not found")
    try:
        output = deliver_output_video(db, output_video_id=output.id, target=payload.target)
    except ValueError as exc:
        failed_output = record_output_delivery_failure(
            db,
            output_video_id=output.id,
            target=payload.target,
            error_message=str(exc),
            phase="manual_delivery",
        )
        if failed_output is not None:
            audit(
                db,
                user_id=user.id,
                project_id=project.id,
                action="output.delivery.failed",
                correlation_id=request.state.correlation_id,
                metadata={"output_video_id": failed_output.id, "target": failed_output.delivery_target},
            )
            db.commit()
        record_workflow_event("delivery", "failed")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="output.delivery.completed",
        correlation_id=request.state.correlation_id,
        metadata={"output_video_id": output.id, "target": output.delivery_target, "status": output.delivery_status},
    )
    db.commit()
    record_workflow_event("delivery", "succeeded")
    return None


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
                "file_size_bytes": row.file_size_bytes,
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


@router.get("/{project_id}/usage", response_model=ProjectUsageResponse)
def project_usage(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="operator", request=request, requested_action="project.usage.read"
    )
    return ProjectUsageResponse(**project_usage_summary(db, project_id=project.id))


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
    record_workflow_event("retention_cleanup", "previewed" if payload.dry_run else "completed")
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


@router.get("/{project_id}/members", response_model=ProjectMembershipsResponse)
def list_project_memberships(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="owner", request=request, requested_action="project.memberships.read"
    )
    members = []
    for membership in db.query(ProjectMember).filter(ProjectMember.project_id == project.id).all():
        if membership.user_id is not None:
            member_user = db.get(User, membership.user_id)
            if member_user is None:
                continue
            members.append(
                ProjectMembershipRead(
                    id=membership.id,
                    principal_type="user",
                    principal_id=member_user.id,
                    principal_name=member_user.email,
                    role=membership.role,
                )
            )
        elif membership.team_id is not None:
            team = db.get(Team, membership.team_id)
            if team is None:
                continue
            members.append(
                ProjectMembershipRead(
                    id=membership.id,
                    principal_type="team",
                    principal_id=team.id,
                    principal_name=team.name,
                    role=membership.role,
                )
            )
    return ProjectMembershipsResponse(members=members)


@router.put("/{project_id}/members/users/{member_user_id}", response_model=ProjectMembershipRead)
def upsert_project_user_membership(
    project_id: str,
    member_user_id: str,
    payload: MembershipRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="owner", request=request, requested_action="project.membership.user.write"
    )
    member_user = db.get(User, member_user_id)
    if member_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return save_project_user_membership(
        db,
        project=project,
        member_user=member_user,
        role=payload.role,
        user=user,
        correlation_id=request.state.correlation_id,
    )


@router.put("/{project_id}/members/users", response_model=ProjectMembershipRead)
def upsert_project_user_membership_by_email(
    project_id: str,
    payload: UserMembershipRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="owner", request=request, requested_action="project.membership.user.write"
    )
    member_user = db.query(User).filter(User.email == payload.email.strip().lower()).one_or_none()
    if member_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return save_project_user_membership(
        db,
        project=project,
        member_user=member_user,
        role=payload.role,
        user=user,
        correlation_id=request.state.correlation_id,
    )


def save_project_user_membership(
    db: Session,
    *,
    project: Project,
    member_user: User,
    role: str,
    user: CurrentUser,
    correlation_id: str,
) -> ProjectMembershipRead:
    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == member_user.id)
        .one_or_none()
    )
    if membership is None:
        membership = ProjectMember(project_id=project.id, user_id=member_user.id, role=role)
        db.add(membership)
    else:
        membership.role = role
    db.flush()
    audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="project.membership.user.updated",
        correlation_id=correlation_id,
        metadata={"member_user_id": member_user.id, "role": role},
    )
    db.commit()
    return ProjectMembershipRead(
        id=membership.id,
        principal_type="user",
        principal_id=member_user.id,
        principal_name=member_user.email,
        role=membership.role,
    )


@router.delete("/{project_id}/members/users/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_user_membership(
    project_id: str,
    member_user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="owner", request=request, requested_action="project.membership.user.delete"
    )
    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == member_user_id)
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project membership not found")
    db.delete(membership)
    audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="project.membership.user.deleted",
        correlation_id=request.state.correlation_id,
        metadata={"member_user_id": member_user_id},
    )
    db.commit()
    return None


@router.put("/{project_id}/members/teams/{team_id}", response_model=ProjectMembershipRead)
def upsert_project_team_membership(
    project_id: str,
    team_id: str,
    payload: MembershipRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="owner", request=request, requested_action="project.membership.team.write"
    )
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.team_id == team.id)
        .one_or_none()
    )
    if membership is None:
        membership = ProjectMember(project_id=project.id, team_id=team.id, role=payload.role)
        db.add(membership)
    else:
        membership.role = payload.role
    db.flush()
    audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="project.membership.team.updated",
        correlation_id=request.state.correlation_id,
        metadata={"team_id": team.id, "role": payload.role},
    )
    db.commit()
    return ProjectMembershipRead(
        id=membership.id,
        principal_type="team",
        principal_id=team.id,
        principal_name=team.name,
        role=membership.role,
    )


@router.delete("/{project_id}/members/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_team_membership(
    project_id: str,
    team_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    project = get_project_for_role_or_404(
        db, project_id, user, minimum_role="owner", request=request, requested_action="project.membership.team.delete"
    )
    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.team_id == team_id)
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project membership not found")
    db.delete(membership)
    audit(
        db,
        user_id=user.id,
        project_id=project.id,
        action="project.membership.team.deleted",
        correlation_id=request.state.correlation_id,
        metadata={"team_id": team_id},
    )
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
