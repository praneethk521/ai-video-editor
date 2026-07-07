from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import RenderJob, TimelinePlan


def enqueue_render_jobs(db: Session, *, project_id: str, variants: list[str]) -> list[RenderJob]:
    allowed = {"youtube_16x9", "shorts_9x16"}
    requested = [variant for variant in variants if variant in allowed]
    if not requested:
        raise ValueError("no supported variants requested")

    jobs = []
    for variant in requested:
        plan = (
            db.query(TimelinePlan)
            .filter(TimelinePlan.project_id == project_id, TimelinePlan.variant == variant)
            .order_by(TimelinePlan.created_at.desc())
            .first()
        )
        if plan is None:
            raise ValueError(f"timeline plan missing for {variant}")
        job = RenderJob(project_id=project_id, timeline_plan_id=plan.id, variant=variant)
        db.add(job)
        jobs.append(job)
    return jobs

