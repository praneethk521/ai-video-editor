from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.entities import AnalysisResult, MediaAsset, TimelinePlan

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
