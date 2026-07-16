from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.api import (
    MalwareScanResultRequest,
    OutputDeliverRequest,
    OutputDeliveryRequest,
    WorkerRenderCompleteRequest,
    WorkerRenderFailedRequest,
)
from app.services.audit import audit
from app.services.analysis_providers import get_analysis_provider, get_analysis_provider_metrics
from app.services.malware import record_malware_scan_result, scan_media_asset
from app.services.output_delivery import deliver_output_video, record_output_delivery
from app.services.rendering import complete_render_job, fail_render_job, mark_render_job_running

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/analysis-provider/health")
def analysis_provider_health(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    health = get_analysis_provider().health()
    audit(
        db,
        user_id=user.id,
        project_id=None,
        action="analysis.provider.health",
        correlation_id=request.state.correlation_id,
        metadata={"provider": health.provider, "status": health.status},
    )
    db.commit()
    return {"provider": health.provider, "status": health.status, "details": health.details}


@router.get("/analysis-provider/metrics")
def analysis_provider_metrics(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    metrics = get_analysis_provider_metrics()
    audit(
        db,
        user_id=user.id,
        project_id=None,
        action="analysis.provider.metrics",
        correlation_id=request.state.correlation_id,
        metadata={"provider_count": len(metrics["providers"])},
    )
    db.commit()
    return metrics


@router.post("/render-jobs/{render_job_id}/running", status_code=status.HTTP_204_NO_CONTENT)
def render_job_running(
    render_job_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        job = mark_render_job_running(db, render_job_id=render_job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=job.project_id,
        action="render.job.running",
        correlation_id=request.state.correlation_id,
        metadata={"render_job_id": render_job_id, "variant": job.variant},
    )
    db.commit()
    return None


@router.post("/media-assets/{media_asset_id}/malware-scan", status_code=status.HTTP_204_NO_CONTENT)
def media_asset_malware_scan(
    media_asset_id: str,
    payload: MalwareScanResultRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        asset = record_malware_scan_result(
            db,
            media_asset_id=media_asset_id,
            status=payload.status,
            scanner=payload.scanner,
            details=payload.details,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=asset.project_id,
        action="media.malware_scan.recorded",
        correlation_id=request.state.correlation_id,
        metadata={"media_asset_id": media_asset_id, "scanner": payload.scanner, "status": payload.status},
    )
    db.commit()
    return None


@router.post("/media-assets/{media_asset_id}/scan", status_code=status.HTTP_204_NO_CONTENT)
def scan_media_asset_for_malware(
    media_asset_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        asset = scan_media_asset(db, media_asset_id=media_asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=asset.project_id,
        action="media.malware_scan.completed",
        correlation_id=request.state.correlation_id,
        metadata={"media_asset_id": media_asset_id, "status": asset.malware_scan_status},
    )
    db.commit()
    return None


@router.post("/render-jobs/{render_job_id}/complete", status_code=status.HTTP_204_NO_CONTENT)
def render_job_complete(
    render_job_id: str,
    payload: WorkerRenderCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        output = complete_render_job(db, render_job_id=render_job_id, result=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=output.project_id,
        action="render.job.completed",
        correlation_id=request.state.correlation_id,
        metadata={
            "render_job_id": render_job_id,
            "variant": output.variant,
            "private_locator": output.private_locator,
            "validation_status": (output.validation_json or {}).get("status"),
        },
    )
    db.commit()
    return None


@router.post("/render-jobs/{render_job_id}/fail", status_code=status.HTTP_204_NO_CONTENT)
def render_job_fail(
    render_job_id: str,
    payload: WorkerRenderFailedRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        job = fail_render_job(db, render_job_id=render_job_id, error_message=payload.error_message)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=job.project_id,
        action="render.job.failed",
        correlation_id=request.state.correlation_id,
        metadata={"render_job_id": render_job_id, "variant": job.variant},
    )
    db.commit()
    return None


@router.post("/output-videos/{output_video_id}/delivery", status_code=status.HTTP_204_NO_CONTENT)
def output_video_delivery(
    output_video_id: str,
    payload: OutputDeliveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        output = record_output_delivery(
            db,
            output_video_id=output_video_id,
            target=payload.target,
            status=payload.status,
            delivered_locator=payload.delivered_locator,
            details=payload.details,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=output.project_id,
        action="output.delivery.recorded",
        correlation_id=request.state.correlation_id,
        metadata={"output_video_id": output.id, "target": output.delivery_target, "status": output.delivery_status},
    )
    db.commit()
    return None


@router.post("/output-videos/{output_video_id}/deliver", status_code=status.HTTP_204_NO_CONTENT)
def output_video_deliver(
    output_video_id: str,
    payload: OutputDeliverRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        output = deliver_output_video(db, output_video_id=output_video_id, target=payload.target)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    audit(
        db,
        user_id=user.id,
        project_id=output.project_id,
        action="output.delivery.completed",
        correlation_id=request.state.correlation_id,
        metadata={"output_video_id": output.id, "target": output.delivery_target, "status": output.delivery_status},
    )
    db.commit()
    return None
