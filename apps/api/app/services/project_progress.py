from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import AnalysisResult, MediaAsset, OutputVideo, PlanStatus, RenderJob, RenderStatus, TimelinePlan


VARIANTS = ("youtube_16x9", "shorts_9x16")


def derive_project_pipeline(db: Session, *, project_id: str) -> dict:
    media_count = db.query(MediaAsset).filter(
        MediaAsset.project_id == project_id,
        ~MediaAsset.mime_type.like("audio/%"),
    ).count()
    analysis_count = db.query(AnalysisResult).filter(AnalysisResult.project_id == project_id).count()
    plans = (
        db.query(TimelinePlan)
        .filter(TimelinePlan.project_id == project_id)
        .order_by(TimelinePlan.created_at.desc(), TimelinePlan.id.desc())
        .all()
    )
    latest_plans = _latest_by(plans, lambda row: row.variant)
    curated_count = sum(bool((plan.plan_json or {}).get("selection")) for plan in latest_plans.values())
    approved_count = sum(plan.status == PlanStatus.approved for plan in latest_plans.values())

    jobs = (
        db.query(RenderJob)
        .filter(RenderJob.project_id == project_id)
        .order_by(RenderJob.created_at.desc(), RenderJob.id.desc())
        .all()
    )
    latest_jobs = _latest_by(jobs, lambda row: row.variant)
    render_failed = any(job.status == RenderStatus.failed for job in latest_jobs.values())
    render_active = any(job.status in {RenderStatus.queued, RenderStatus.running} for job in latest_jobs.values())
    rendered_count = sum(job.status == RenderStatus.succeeded for job in latest_jobs.values())

    valid_output_jobs = {
        output.render_job_id
        for output in db.query(OutputVideo).filter(OutputVideo.project_id == project_id).all()
        if (output.validation_json or {}).get("status") == "passed"
    }
    ready_count = sum(
        job.status == RenderStatus.succeeded and job.id in valid_output_jobs
        for job in latest_jobs.values()
    )

    steps = [
        _step("import", "Import", media_count > 0, f"{media_count} media items" if media_count else "No media yet"),
        _step("analyze", "Analyze", analysis_count > 0, f"{analysis_count} analysis run{'s' if analysis_count != 1 else ''}"),
        _step("curate", "Curate", curated_count == len(VARIANTS), f"{curated_count}/{len(VARIANTS)} story plans"),
        _step("review", "Review", approved_count == len(VARIANTS), f"{approved_count}/{len(VARIANTS)} formats approved"),
        _step("render", "Render", rendered_count == len(VARIANTS), f"{rendered_count} formats rendered"),
        _step("ready", "Ready", ready_count == len(VARIANTS), f"{ready_count} validated outputs"),
    ]

    render = steps[4]
    if render_failed:
        render["state"] = "failed"
        render["detail"] = "Latest render attempt failed"
        current_step, next_action = "render", "Retry the failed render"
    elif render_active:
        render["state"] = "current"
        render["detail"] = "Render is queued or running"
        current_step, next_action = "render", "Wait for rendering to finish"
    else:
        current_step, next_action = _mark_current_step(steps)

    return {"current_step": current_step, "next_action": next_action, "steps": steps}


def _latest_by(rows: list, key) -> dict:
    latest = {}
    for row in rows:
        latest.setdefault(key(row), row)
    return latest


def _step(identifier: str, label: str, complete: bool, detail: str) -> dict:
    return {"id": identifier, "label": label, "state": "complete" if complete else "pending", "detail": detail}


def _mark_current_step(steps: list[dict]) -> tuple[str, str]:
    actions = {
        "import": "Import photos and videos",
        "analyze": "Analyze the imported media",
        "curate": "Generate story-focused plans",
        "review": "Review and approve both formats",
        "render": "Render the approved videos",
        "ready": "Preview or download the finished videos",
    }
    first_incomplete = next((step for step in steps if step["state"] != "complete"), None)
    if first_incomplete is None:
        return "ready", actions["ready"]
    first_incomplete["state"] = "current"
    return first_incomplete["id"], actions[first_incomplete["id"]]
