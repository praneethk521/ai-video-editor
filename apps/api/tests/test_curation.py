import math

import pytest

from app.services.local_analysis import SIDE, inspect_pixels
from app.services.planning import create_timeline_plans, approve_timeline_plan
from app.models.entities import PlanStatus
from video_shared.curation import select_candidates


def candidate(name, score=0.8, **extra):
    return {"asset_id": name, "mime_type": "image/jpeg", "duration_seconds": 3,
            "quality": {"score": score, "usable": True}, **extra}


def test_large_album_obeys_budget_and_preserves_import_order():
    result = select_candidates([candidate(str(i), score=(i + 1) / 500) for i in range(500)],
                               target_seconds=30, max_clip_seconds=3)
    assert result["duration_seconds"] == 30
    assert [item["asset_id"] for item in result["selected"]] == [str(i) for i in range(490, 500)]
    assert len(result["decisions"]) == 500


def test_best_duplicate_wins_and_bad_quality_requires_review():
    items = [candidate("soft", 0.4, duplicate_group="same"), candidate("sharp", 0.9, duplicate_group="same"),
             candidate("dark", quality={"score": 0.1, "usable": False, "flags": ["severe_underexposure"]})]
    result = select_candidates(items, target_seconds=30, max_clip_seconds=3)
    assert [item["asset_id"] for item in result["selected"]] == ["sharp"]
    assert result["decisions"][0]["alternative_to"] == "sharp"
    assert result["decisions"][2]["status"] == "review"


def test_nonzero_video_trim_and_short_source_are_bounded():
    result = select_candidates([candidate("clip", mime_type="video/mp4", duration_seconds=10, recommended_start=8.5)],
                               target_seconds=30, max_clip_seconds=8)
    assert result["selected"][0]["selected_start"] == 8.5
    assert result["duration_seconds"] == 1.5


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -1])
def test_invalid_scores_fail(invalid):
    with pytest.raises(ValueError):
        select_candidates([candidate("bad", invalid)], target_seconds=30, max_clip_seconds=3)


def test_all_bad_does_not_fabricate_selection():
    result = select_candidates([candidate("bad", quality={"score": 0, "usable": False})], target_seconds=30, max_clip_seconds=3)
    assert result["selected"] == []
    assert result["duration_seconds"] == 0


def test_pixel_quality_uses_content_not_filename():
    dark = inspect_pixels(bytes(SIDE * SIDE))
    texture = inspect_pixels(bytes(50 if (x // 4 + y // 4) % 2 else 200 for y in range(SIDE) for x in range(SIDE)))
    assert not dark["usable"]
    assert "severe_underexposure" in dark["flags"]
    assert texture["usable"]
    assert texture["score"] > dark["score"]
    assert texture["eye_state"] == "unknown"
    assert texture["landmark"] == "unknown"


def test_invalid_frame_size_rejected():
    with pytest.raises(ValueError, match="complete preview"):
        inspect_pixels(b"invalid")


def test_curated_plan_budget_and_regeneration_invalidates_approval(client, auth_headers, db_session):
    project_id = client.post("/projects", headers=auth_headers, json={"name": "Curation"}).json()["id"]
    analysis = {"provider": "local-pixel-quality-v1", "asset_features": [candidate(str(i)) for i in range(20)]}
    first = create_timeline_plans(db_session, project_id=project_id, analysis_json=analysis,
                                  variants=["shorts_9x16"], targets={"shorts_9x16": 15})[0]
    db_session.flush()
    assert len(first.plan_json["tracks"][0]["clips"]) == 5
    assert first.plan_json["selection"]["duration_seconds"] == 15
    approve_timeline_plan(db_session, project_id=project_id, plan_id=first.id, notes=None)
    create_timeline_plans(db_session, project_id=project_id, analysis_json=analysis, variants=["shorts_9x16"])
    assert first.status == PlanStatus.rejected
