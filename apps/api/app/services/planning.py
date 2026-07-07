from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.entities import AnalysisResult, MediaAsset, PlanStatus, Project, ProjectStatus, TimelinePlan, utcnow
from app.services.malware import require_clean_media_assets

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

from video_shared.timeline import AssetSummary, build_timeline_plan  # noqa: E402


def analyze_and_plan(db: Session, *, project_id: str) -> tuple[AnalysisResult, list[TimelinePlan]]:
    assets = db.query(MediaAsset).filter(MediaAsset.project_id == project_id).all()
    if not assets:
        raise ValueError("project has no media assets")
    require_clean_media_assets(assets)

    asset_summaries = [
        AssetSummary(
            asset_id=asset.id,
            duration_seconds=asset.duration_seconds or 3,
            orientation=asset.orientation,
            highlight_score=0.8 if asset.mime_type.startswith("video/") else 0.6,
        )
        for asset in assets
    ]
    result = AnalysisResult(
        project_id=project_id,
        provider="deterministic-local-baseline",
        result_json={
            "scene_count": len(assets),
            "faces_detected": "provider_pending",
            "audio_quality": "provider_pending",
            "duplicate_clip_detection": "provider_pending",
            "safety_note": "No private media bytes are included in this metadata record.",
        },
    )
    db.add(result)

    plans = []
    for variant in ("youtube_16x9", "shorts_9x16"):
        plan_json = build_timeline_plan(project_id, asset_summaries, variant)
        plan = TimelinePlan(
            project_id=project_id,
            variant=variant,
            confidence_score=plan_json["confidence_score"],
            plan_json=plan_json,
        )
        db.add(plan)
        plans.append(plan)
    return result, plans


def list_timeline_plans(db: Session, *, project_id: str) -> list[TimelinePlan]:
    return (
        db.query(TimelinePlan)
        .filter(TimelinePlan.project_id == project_id)
        .order_by(TimelinePlan.created_at.desc())
        .all()
    )


def approve_timeline_plan(db: Session, *, project_id: str, plan_id: str, notes: str | None) -> TimelinePlan:
    plan = get_project_plan(db, project_id=project_id, plan_id=plan_id)
    plan.status = PlanStatus.approved
    plan.review_notes = notes
    plan.approved_at = utcnow()
    reject_other_variant_plans(db, project_id=project_id, plan=plan)
    project = db.get(Project, project_id)
    if project is not None:
        project.status = ProjectStatus.planned
    return plan


def reject_timeline_plan(db: Session, *, project_id: str, plan_id: str, notes: str | None) -> TimelinePlan:
    plan = get_project_plan(db, project_id=project_id, plan_id=plan_id)
    plan.status = PlanStatus.rejected
    plan.review_notes = notes
    return plan


def regenerate_timeline_plans(db: Session, *, project_id: str, variants: list[str], notes: str | None) -> list[TimelinePlan]:
    assets = db.query(MediaAsset).filter(MediaAsset.project_id == project_id).all()
    if not assets:
        raise ValueError("project has no media assets")
    require_clean_media_assets(assets)

    allowed = {"youtube_16x9", "shorts_9x16"}
    requested = [variant for variant in variants if variant in allowed]
    if not requested:
        raise ValueError("no supported variants requested")

    asset_summaries = [
        AssetSummary(
            asset_id=asset.id,
            duration_seconds=asset.duration_seconds or 3,
            orientation=asset.orientation,
            highlight_score=0.8 if asset.mime_type.startswith("video/") else 0.6,
        )
        for asset in assets
    ]
    plans = []
    for variant in requested:
        plan_json = build_timeline_plan(project_id, asset_summaries, variant)
        plan_json["strategy"]["review_notes"] = notes or "Regenerated from reviewer request."
        plan = TimelinePlan(
            project_id=project_id,
            variant=variant,
            confidence_score=plan_json["confidence_score"],
            plan_json=plan_json,
            review_notes=notes,
        )
        db.add(plan)
        plans.append(plan)
    project = db.get(Project, project_id)
    if project is not None:
        project.status = ProjectStatus.planned
    return plans


def get_project_plan(db: Session, *, project_id: str, plan_id: str) -> TimelinePlan:
    plan = db.get(TimelinePlan, plan_id)
    if plan is None or plan.project_id != project_id:
        raise ValueError("timeline plan not found")
    return plan


def reject_other_variant_plans(db: Session, *, project_id: str, plan: TimelinePlan) -> None:
    rows = (
        db.query(TimelinePlan)
        .filter(
            TimelinePlan.project_id == project_id,
            TimelinePlan.variant == plan.variant,
            TimelinePlan.id != plan.id,
            TimelinePlan.status == PlanStatus.approved,
        )
        .all()
    )
    for row in rows:
        row.status = PlanStatus.rejected
