from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.tracing import operation_span
from app.core.config import settings
from app.models.entities import AnalysisResult, MediaAsset, PlanStatus, Project, ProjectStatus, TimelinePlan, utcnow
from app.services.analysis_providers import ProjectAnalysis, get_analysis_provider
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
from video_shared.curation import select_candidates  # noqa: E402


def analyze_and_plan(db: Session, *, project_id: str) -> tuple[AnalysisResult, list[TimelinePlan]]:
    assets = db.query(MediaAsset).filter(MediaAsset.project_id == project_id).order_by(MediaAsset.created_at, MediaAsset.id).all()
    if not assets:
        raise ValueError("project has no media assets")
    require_clean_media_assets(assets)

    analysis = analyze_with_tracing(assets)
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


def update_timeline_plan(
    db: Session,
    *,
    project_id: str,
    plan_id: str,
    decisions: list[dict],
    notes: str | None,
) -> TimelinePlan:
    plan = get_project_plan(db, project_id=project_id, plan_id=plan_id)
    selection = plan.plan_json.get("selection")
    if not selection:
        raise ValueError("timeline plan does not support selection review")
    existing = {item["asset_id"]: item for item in selection.get("decisions", [])}
    supplied_ids = [item["asset_id"] for item in decisions]
    if len(supplied_ids) != len(set(supplied_ids)) or set(supplied_ids) != set(existing):
        raise ValueError("selection review must contain each plan asset exactly once")
    assets = {
        asset.id: asset
        for asset in db.query(MediaAsset).filter(
            MediaAsset.project_id == project_id,
            MediaAsset.id.in_(supplied_ids),
        )
    }
    if set(assets) != set(existing):
        raise ValueError("selection review contains unavailable media")

    reviewed = []
    selected = []
    total = 0.0
    old_clips = {
        clip["asset_id"]: clip
        for track in plan.plan_json.get("tracks", [])
        if track.get("type") == "video"
        for clip in track.get("clips", [])
    }
    for item in decisions:
        asset = assets[item["asset_id"]]
        is_selected = bool(item["selected"] or item.get("pinned"))
        start = round(float(item["start"]), 2)
        duration = round(float(item["duration"]), 2)
        source_duration = float(asset.duration_seconds or 3)
        if asset.mime_type.startswith("image/"):
            start = 0.0
        elif start + duration > source_duration + 1e-8:
            raise ValueError(f"trim exceeds source duration for {asset.original_filename}")
        reasons = [reason for reason in existing[item["asset_id"]].get("reasons", [])
                   if not reason.startswith("owner_")]
        reasons.append("owner_pinned" if item.get("pinned") else
                       "owner_included" if is_selected else "owner_excluded")
        decision = {
            **existing[item["asset_id"]],
            "status": "selected" if is_selected else "excluded",
            "reasons": list(dict.fromkeys(reasons)),
            "pinned": bool(item.get("pinned")),
        }
        if is_selected:
            decision.update(start=start, duration=duration)
            selected.append((asset, decision, old_clips.get(asset.id, {})))
            total += duration
        else:
            decision.pop("start", None)
            decision.pop("duration", None)
        reviewed.append(decision)
    if not selected:
        raise ValueError("selection review must include at least one media item")
    if total > float(selection["target_seconds"]) + 1e-8:
        raise ValueError("selected media exceeds the plan duration target")

    timeline_start = 0.0
    clips = []
    for asset, decision, old_clip in selected:
        duration = decision["duration"]
        clips.append({
            "asset_id": asset.id,
            "start": decision["start"],
            "end": round(decision["start"] + duration, 2),
            "timeline_start": round(timeline_start, 2),
            "effect": old_clip.get("effect", "cut"),
            "caption": old_clip.get("caption", ""),
            "crop_strategy": old_clip.get("crop_strategy", "center"),
        })
        timeline_start += duration

    plan_json = dict(plan.plan_json)
    plan_json["version"] = int(plan_json.get("version", 1)) + 1
    plan_json["tracks"] = [{"type": "video", "clips": clips}]
    plan_json["strategy"] = {
        **(plan_json.get("strategy") or {}),
        "hook": "Owner-reviewed local selection with explicit include, exclude, pin and trim decisions.",
    }
    plan_json["selection"] = {
        **selection,
        "method": "owner_reviewed_v1",
        "duration_seconds": round(total, 2),
        "decisions": reviewed,
    }
    plan.plan_json = plan_json
    plan.status = PlanStatus.draft
    plan.review_notes = notes
    plan.approved_at = None
    project = db.get(Project, project_id)
    if project is not None:
        project.status = ProjectStatus.planned
    return plan


def regenerate_timeline_plans(db: Session, *, project_id: str, variants: list[str], notes: str | None,
                             targets: dict | None = None) -> list[TimelinePlan]:
    assets = db.query(MediaAsset).filter(MediaAsset.project_id == project_id).order_by(MediaAsset.created_at, MediaAsset.id).all()
    if not assets:
        raise ValueError("project has no media assets")
    require_clean_media_assets(assets)

    allowed = {"youtube_16x9", "shorts_9x16"}
    requested = [variant for variant in variants if variant in allowed]
    if not requested:
        raise ValueError("no supported variants requested")

    analysis_result = latest_analysis_result(db, project_id=project_id)
    if analysis_result is None:
        analysis = analyze_with_tracing(assets)
        analysis_result = AnalysisResult(project_id=project_id, provider=analysis.provider, result_json=analysis.result)
        db.add(analysis_result)

    plans = create_timeline_plans(
        db,
        project_id=project_id,
        analysis_json=analysis_result.result_json,
        variants=requested,
        notes=notes,
        targets=targets,
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
    targets: dict | None = None,
) -> list[TimelinePlan]:
    asset_summaries = asset_summaries_from_analysis(analysis_json)
    db.flush()
    plans = []
    for variant in variants:
        local_curation = analysis_json.get("provider") in {"local-pixel-quality-v1", "local-vision-curation-v1"}
        selection = None
        if local_curation:
            target = settings.landscape_target_seconds if variant == "youtube_16x9" else settings.portrait_target_seconds
            target = (targets or {}).get(variant) or target
            selection = select_candidates(analysis_json["asset_features"], target_seconds=target,
                                          max_clip_seconds=8 if variant == "youtube_16x9" else 3)
            if not selection["selected"]:
                raise ValueError("no automatically usable media; quality review is required before planning")
            asset_summaries = [AssetSummary(asset_id=item["asset_id"], duration_seconds=item["selected_duration"],
                                            source_start=item["selected_start"]) for item in selection["selected"]]
        plan_json = build_timeline_plan(project_id, asset_summaries, variant, curated=local_curation)
        if selection is not None:
            plan_json["selection"] = {key: value for key, value in selection.items() if key != "selected"}
            plan_json["export"]["max_duration_seconds"] = int(selection["target_seconds"])
            plan_json["strategy"]["hook"] = (
                "Local vision selection with technical, semantic and diversity evidence; owner review required."
                if analysis_json.get("provider") == "local-vision-curation-v1" else
                "Local technical-quality selection; semantic and eye-state review still required."
            )
        if notes is not None:
            plan_json["strategy"]["review_notes"] = notes or "Regenerated from reviewer request."
        for approved in db.query(TimelinePlan).filter(TimelinePlan.project_id == project_id,
                                                      TimelinePlan.variant == variant,
                                                      TimelinePlan.status == PlanStatus.approved).all():
            approved.status = PlanStatus.rejected
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


def analyze_with_tracing(assets: list[MediaAsset]) -> ProjectAnalysis:
    if any((asset.metadata_json or {}).get("relative_path") for asset in assets):
        from app.services.local_analysis import analyze_local_media
        provider = "local-vision-curation-v1" if settings.local_vision_enabled else "local-pixel-quality-v1"
        with operation_span("analysis.provider", attributes={"analysis.provider": provider}):
            return analyze_local_media(assets)
    provider = get_analysis_provider()
    with operation_span("analysis.provider", attributes={"analysis.provider": provider.provider_name}):
        return provider.analyze(assets)


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
