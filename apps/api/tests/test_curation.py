import math
from datetime import UTC, datetime, timedelta

import pytest

from app.services.local_analysis import SIDE, inspect_pixels
from app.services import local_vision
from app.services.local_vision import VisionEvidence, conservative_evidence, feature_fields
from app.services.planning import create_timeline_plans, approve_timeline_plan
from app.models.entities import MediaAsset, PlanStatus
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


def test_semantic_selection_prefers_story_diversity_and_capture_order():
    items = [
        candidate("geyser-best", 0.9, editorial_score=0.95, story_group="landmark:geothermal",
                  capture_time="2026-01-02T12:00:00Z", semantic={"confidence": 0.9}),
        candidate("geyser-second", 0.9, editorial_score=0.94, story_group="landmark:geothermal",
                  capture_time="2026-01-01T12:00:00Z", semantic={"confidence": 0.9}),
        candidate("waterfall", 0.7, editorial_score=0.75, story_group="landscape:waterfall",
                  capture_time="2026-01-03T12:00:00Z", semantic={"confidence": 0.8}),
    ]
    result = select_candidates(items, target_seconds=6, max_clip_seconds=3)
    assert [item["asset_id"] for item in result["selected"]] == ["geyser-best", "waterfall"]
    assert result["method"] == "local_story_curation_v2"


def test_semantic_selection_does_not_pad_with_one_repeated_story():
    items = [
        candidate(f"geyser-{index}", 0.95 - index / 100, editorial_score=0.95 - index / 100,
                  story_group="landmark:geothermal", semantic={"confidence": 0.9},
                  capture_time=f"2026-01-01T12:00:0{index}Z")
        for index in range(5)
    ] + [
        candidate("waterfall", 0.8, editorial_score=0.8, story_group="landscape:waterfall",
                  semantic={"confidence": 0.9}, capture_time="2026-01-01T13:00:00Z")
    ]

    result = select_candidates(items, target_seconds=30, max_clip_seconds=3)

    assert [item["asset_id"] for item in result["selected"]] == ["geyser-0", "geyser-1", "waterfall"]
    decisions = {item["asset_id"]: item for item in result["decisions"]}
    assert decisions["geyser-2"]["reasons"] == ["semantic_repetition"]
    assert result["story"]["semantic_repetitions_suppressed"] == 3
    assert result["story"]["story_groups_covered"] == 2


def test_confident_closed_eyes_are_held_for_review():
    closed = candidate("closed", editorial_score=0.99,
                       semantic={"confidence": 0.9, "eye_state": "closed", "occlusion": "none"})
    open_photo = candidate("open", editorial_score=0.8,
                           semantic={"confidence": 0.9, "eye_state": "open", "occlusion": "none"})
    result = select_candidates([closed, open_photo], target_seconds=6, max_clip_seconds=3)
    assert [item["asset_id"] for item in result["selected"]] == ["open"]
    assert result["decisions"][0]["status"] == "review"
    assert "eye_state_review" in result["decisions"][0]["reasons"]


def test_local_vision_downgrades_uncertain_face_claims():
    evidence = VisionEvidence(
        scene="group", setting="outdoor", people_count=2, face_visibility="partial", eye_state="closed",
        occlusion="minor", point_of_interest="scenic_background", landmark_hint="A famous place",
        editorial_relevance=0.8, moment_quality=0.7, tags=["people", "scenery"], confidence=0.65,
        needs_review=False,
    )
    conservative = conservative_evidence(evidence)
    assert conservative.eye_state == "uncertain"
    assert conservative.needs_review is True
    assert feature_fields(conservative)["story_group"] == "group:people"


def test_local_vision_rejects_cross_field_wildlife_claim():
    evidence = VisionEvidence(
        scene="landscape", setting="outdoor", people_count=0, face_visibility="no_people",
        eye_state="no_people", occlusion="none", point_of_interest="wildlife",
        landmark_hint=None, editorial_relevance=0.8, moment_quality=0.8,
        tags=["waterfall", "scenery"], confidence=0.9, needs_review=False,
    )
    conservative = conservative_evidence(evidence)
    assert conservative.point_of_interest == "natural_landmark"
    assert feature_fields(conservative)["story_group"] == "landscape:waterfall"


@pytest.mark.parametrize("url", ["https://example.com:11434", "http://192.168.1.10:11434",
                                 "http://localhost:9000", "http://user@localhost:11434"])
def test_local_vision_rejects_non_loopback_endpoints(monkeypatch, url):
    monkeypatch.setattr(local_vision.settings, "local_vision_url", url)
    with pytest.raises(local_vision.LocalVisionError, match="loopback"):
        local_vision.endpoint()


def test_local_vision_normalizes_ten_point_model_scores(monkeypatch):
    content = VisionEvidence(
        scene="landmark", setting="outdoor", people_count=0, face_visibility="no_people",
        eye_state="no_people", occlusion="none", point_of_interest="natural_landmark",
        landmark_hint="geothermal spring", editorial_relevance=0.7, moment_quality=0.8,
        tags=["geothermal", "scenery"], confidence=0.9, needs_review=False,
    ).model_dump()
    content.update(editorial_relevance=7, moment_quality=8, confidence=9)

    class Response:
        is_success = True
        content = b"response"

        def json(self):
            return {"message": {"content": __import__("json").dumps(content)}}

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs): return Response()

    monkeypatch.setattr(local_vision.httpx, "Client", Client)
    result = local_vision.analyze_preview(b"\xff\xd8preview")
    assert result.editorial_relevance == 0.7
    assert result.moment_quality == 0.8
    assert result.confidence == 0.9


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


def test_new_plan_defaults_to_latest_project_soundtrack(client, auth_headers, db_session):
    project_id = client.post("/projects", headers=auth_headers, json={"name": "Soundtrack"}).json()["id"]
    started = datetime.now(UTC)
    older = MediaAsset(
        project_id=project_id, original_filename="older.mp3", sanitized_filename="older.mp3",
        mime_type="audio/mpeg", size_bytes=100, duration_seconds=60, orientation="audio",
        private_locator=f"file://private/sources/{project_id}/older", malware_scan_status="clean",
        metadata_json={}, created_at=started,
    )
    newer = MediaAsset(
        project_id=project_id, original_filename="newer.wav", sanitized_filename="newer.wav",
        mime_type="audio/wav", size_bytes=100, duration_seconds=60, orientation="audio",
        private_locator=f"file://private/sources/{project_id}/newer", malware_scan_status="clean",
        metadata_json={}, created_at=started + timedelta(seconds=1),
    )
    db_session.add_all([older, newer])
    db_session.flush()
    analysis = {"provider": "local-pixel-quality-v1", "asset_features": [candidate("photo")]}

    plan = create_timeline_plans(
        db_session, project_id=project_id, analysis_json=analysis, variants=["youtube_16x9"]
    )[0]

    assert plan.plan_json["soundtrack"]["mode"] == "latest"
    assert plan.plan_json["soundtrack"]["asset_id"] == newer.id
    assert plan.plan_json["tracks"][1]["type"] == "audio"
