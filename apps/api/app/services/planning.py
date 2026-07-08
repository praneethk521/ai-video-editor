from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.entities import AnalysisResult, MediaAsset, PlanStatus, Project, ProjectStatus, TimelinePlan, utcnow
from app.services.analysis_providers import get_analysis_provider
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

    analysis = get_analysis_provider().analyze(assets)
    result = AnalysisResult(
        project_id=project_id,
        provider=analysis.provider,
        result_json=analysis.result,
    )
    db.add(result)

    return result, create_timeline_plans(
        db,
        project_id=project_id,
        analysis_json=analysis.result,
        variants=["youtube_16x9", "shorts_9x16"],
    )


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

    analysis_result = latest_analysis_result(db, project_id=project_id)
    if analysis_result is None:
        analysis = get_analysis_provider().analyze(assets)
        analysis_result = AnalysisResult(project_id=project_id, provider=analysis.provider, result_json=analysis.result)
        db.add(analysis_result)

    plans = create_timeline_plans(
        db,
        project_id=project_id,
        analysis_json=analysis_result.result_json,
        variants=requested,
        notes=notes,
    )
    project = db.get(Project, project_id)
    if project is not None:
        project.status = ProjectStatus.planned
    return plans


def create_timeline_plans(
    db: Session,
    *,
    project_id: str,
    analysis_json: dict,
    variants: list[str],
    notes: str | None = None,
) -> list[TimelinePlan]:
    asset_summaries = asset_summaries_from_analysis(analysis_json)
    plans = []
    for variant in variants:
        plan_json = build_timeline_plan(project_id, asset_summaries, variant)
        if notes is not None:
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
    return plans


def latest_analysis_result(db: Session, *, project_id: str) -> AnalysisResult | None:
    return (
        db.query(AnalysisResult)
        .filter(AnalysisResult.project_id == project_id)
        .order_by(AnalysisResult.created_at.desc())
        .first()
    )


def list_analysis_results(db: Session, *, project_id: str) -> list[AnalysisResult]:
    return (
        db.query(AnalysisResult)
        .filter(AnalysisResult.project_id == project_id)
        .order_by(AnalysisResult.created_at.desc())
        .all()
    )


def asset_summaries_from_analysis(analysis_json: dict) -> list[AssetSummary]:
    features = analysis_json.get("asset_features") or []
    summaries = []
    for feature in features:
        subject = feature.get("subject") or {}
        audio = feature.get("audio") or {}
        summaries.append(
            AssetSummary(
                asset_id=feature["asset_id"],
                duration_seconds=feature.get("duration_seconds") or 3,
                orientation=feature.get("orientation") or "unknown",
                highlight_score=feature.get("highlight_score") or 0.5,
                scene_count=feature.get("scene_count") or 1,
                subject_presence=subject.get("presence") or "unknown",
                audio_quality=audio.get("quality") or "unknown",
                tags=tuple(feature.get("tags") or ()),
            )
        )
    return summaries


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
