from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException
from opentelemetry.propagate import inject
from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.tracing import operation_span
from app.models.entities import MediaAsset, OutputVideo, PlanStatus, Project, ProjectStatus, RenderJob, RenderStatus, TimelinePlan

from pathlib import Path
import sys


def add_shared_path() -> None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "shared" / "python"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))
            return
    container_candidate = Path("/packages/shared/python")
    if container_candidate.exists() and str(container_candidate) not in sys.path:
        sys.path.append(str(container_candidate))


add_shared_path()

from video_shared import validate_private_locator  # noqa: E402


@dataclass(frozen=True)
class RenderQueueItem:
    render_job_id: str
    plan_json: dict
    sources: dict = field(default_factory=dict)


def enqueue_render_jobs(db: Session, *, project_id: str, variants: list[str]) -> list[RenderJob]:
    jobs, queue_items = create_render_jobs(db, project_id=project_id, variants=variants)
    dispatch_render_jobs(queue_items)
    return jobs


def create_render_jobs(db: Session, *, project_id: str, variants: list[str]) -> tuple[list[RenderJob], list[RenderQueueItem]]:
    allowed = {"youtube_16x9", "shorts_9x16"}
    requested = [variant for variant in variants if variant in allowed]
    if not requested:
        raise ValueError("no supported variants requested")

    jobs = []
    queue_items = []
    for variant in requested:
        plan = (
            db.query(TimelinePlan)
            .filter(
                TimelinePlan.project_id == project_id,
                TimelinePlan.variant == variant,
                TimelinePlan.status == PlanStatus.approved,
            )
            .order_by(TimelinePlan.created_at.desc())
            .first()
        )
        if plan is None:
            raise ValueError(f"approved timeline plan missing for {variant}")
        job = RenderJob(project_id=project_id, timeline_plan_id=plan.id, variant=variant)
        db.add(job)
        db.flush()
        jobs.append(job)
        sources = {}
        if settings.render_queue_backend != "database":
            for track in plan.plan_json["tracks"]:
                for clip in track["clips"]:
                    asset = db.get(MediaAsset, clip["asset_id"])
                    if asset is None or asset.project_id != project_id or asset.malware_scan_status != "clean":
                        raise ValueError("timeline source is not authorized and clean")
                    metadata = asset.metadata_json or {}
                    if not metadata.get("relative_path") or not metadata.get("sha256"):
                        raise ValueError("source is not staged locally; upload the media before rendering")
                    sources[asset.id] = {"relative_path": metadata["relative_path"], "sha256": metadata["sha256"]}
        queue_items.append(RenderQueueItem(render_job_id=job.id, plan_json=plan.plan_json, sources=sources))
    return jobs, queue_items


def dispatch_render_jobs(queue_items: list[RenderQueueItem]) -> None:
    if settings.render_queue_backend == "database":
        return
    if settings.render_queue_backend != "rq":
        raise ValueError(f"unsupported render queue backend: {settings.render_queue_backend}")

    queue = Queue("renders", connection=Redis.from_url(settings.redis_url))
    for item in queue_items:
        variant = normalized_variant(str(item.plan_json.get("variant") or "unknown"))
        with operation_span("render.enqueue", attributes={"video.variant": variant}):
            trace_context: dict[str, str] = {}
            if settings.tracing_enabled:
                inject(trace_context)
            queue.enqueue_call(
                func="app.jobs.render_timeline_job",
                args=(item.render_job_id, item.plan_json),
                kwargs={"trace_context": trace_context, "sources": item.sources},
                timeout=settings.render_job_timeout_seconds,
                result_ttl=86400,
                failure_ttl=86400,
            )


def normalized_variant(variant: str) -> str:
    return variant if variant in {"youtube_16x9", "shorts_9x16"} else "unknown"


def mark_render_job_running(db: Session, *, render_job_id: str) -> RenderJob:
    job = get_render_job(db, render_job_id)
    job.status = RenderStatus.running
    job.error_message = None
    return job


def complete_render_job(db: Session, *, render_job_id: str, result) -> OutputVideo:
    job = get_render_job(db, render_job_id)
    if (result.validation or {}).get("status") != "passed":
        raise ValueError("only validated real renders may complete a job")
    if result.variant != job.variant or result.file_size_bytes <= 0:
        raise ValueError("render output does not match its job")
    private_locator = validate_private_locator(result.private_locator)
    if private_locator.startswith("file://private/") and not private_locator.startswith(f"file://private/{job.project_id}/"):
        raise ValueError("render output belongs to a different project")
    upload_package = result.upload_package or {}
    delivery_target = upload_package.get("delivery_target") or settings.output_storage_provider
    delivery_status = upload_package.get("delivery_status") or "private_staging"
    output = (
        db.query(OutputVideo)
        .filter(OutputVideo.render_job_id == job.id)
        .one_or_none()
    )
    if output is None:
        output = OutputVideo(
            project_id=job.project_id,
            render_job_id=job.id,
            variant=result.variant,
            private_locator=private_locator,
            width=result.width,
            height=result.height,
            duration_seconds=result.duration_seconds,
            file_size_bytes=result.file_size_bytes,
            upload_package_json=upload_package,
            validation_json=result.validation,
            delivery_target=delivery_target,
            delivery_status=delivery_status,
            delivery_json={
                "source_locator": private_locator,
                "manual_upload_only": bool(upload_package.get("manual_upload_only", True)),
            },
        )
        db.add(output)
    else:
        output.variant = result.variant
        output.private_locator = private_locator
        output.width = result.width
        output.height = result.height
        output.duration_seconds = result.duration_seconds
        output.file_size_bytes = result.file_size_bytes
        output.upload_package_json = upload_package
        output.validation_json = result.validation
        output.delivery_target = delivery_target
        output.delivery_status = delivery_status
        output.delivery_json = {
            **(output.delivery_json or {}),
            "source_locator": private_locator,
            "manual_upload_only": bool(upload_package.get("manual_upload_only", True)),
        }

    db.flush()
    if settings.auto_deliver_outputs:
        from app.services.output_delivery import deliver_output_video, record_output_delivery_failure

        try:
            output = deliver_output_video(db, output_video_id=output.id, target=delivery_target)
        except (ValueError, HTTPException) as exc:
            error_message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            output = record_output_delivery_failure(
                db,
                output_video_id=output.id,
                target=delivery_target,
                error_message=error_message,
                phase="auto_delivery",
            ) or output

    job.status = RenderStatus.succeeded
    job.error_message = None
    refresh_project_render_status(db, project_id=job.project_id)
    return output


def fail_render_job(db: Session, *, render_job_id: str, error_message: str) -> RenderJob:
    job = get_render_job(db, render_job_id)
    job.status = RenderStatus.failed
    job.error_message = error_message[:2000]
    project = db.get(Project, job.project_id)
    if project is not None:
        project.status = ProjectStatus.failed
    return job


def get_render_job(db: Session, render_job_id: str) -> RenderJob:
    job = db.get(RenderJob, render_job_id)
    if job is None:
        raise ValueError("render job not found")
    return job


def refresh_project_render_status(db: Session, *, project_id: str) -> None:
    project = db.get(Project, project_id)
    if project is None:
        return
    jobs = (
        db.query(RenderJob)
        .join(TimelinePlan, TimelinePlan.id == RenderJob.timeline_plan_id)
        .filter(
            RenderJob.project_id == project_id,
            TimelinePlan.status == PlanStatus.approved,
        )
        .all()
    )
    if jobs and all(job.status == RenderStatus.succeeded for job in jobs):
        project.status = ProjectStatus.ready
