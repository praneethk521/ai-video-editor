"""Duration-bounded editorial selection from explicit, reviewable evidence."""
from __future__ import annotations

import math


def select_candidates(features: list[dict], *, target_seconds: float, max_clip_seconds: float) -> dict:
    if not math.isfinite(target_seconds) or not 1 <= target_seconds <= 300:
        raise ValueError("target duration must be between 1 and 300 seconds")
    if not math.isfinite(max_clip_seconds) or not 0 < max_clip_seconds <= 8:
        raise ValueError("maximum clip duration must be between 0 and 8 seconds")
    if not 1 <= len(features) <= 500:
        raise ValueError("curation requires 1-500 candidates")
    if len({item["asset_id"] for item in features}) != len(features):
        raise ValueError("candidate identifiers must be unique")
    decisions = {}
    ranked = []
    for index, item in enumerate(features):
        quality = item.get("quality") or {}
        score = item.get("editorial_score", quality.get("score", 0))
        duration = item.get("duration_seconds", 0)
        start = item.get("recommended_start", 0)
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (score, duration, start)):
            raise ValueError("candidate evidence must be finite")
        if not 0 <= score <= 1 or duration <= 0 or not 0 <= start < duration:
            raise ValueError("invalid candidate evidence")
        semantic = item.get("semantic") or {}
        reasons = list(quality.get("flags") or [])
        if semantic.get("needs_review"):
            reasons.append("semantic_review_required")
        if semantic.get("eye_state") in {"closed", "mixed"}:
            reasons.append("eye_state_review")
        if semantic.get("occlusion") == "major":
            reasons.append("major_occlusion_review")
        decisions[item["asset_id"]] = {"asset_id": item["asset_id"], "status": "review",
                                       "reasons": reasons, "score": score}
        if quality.get("usable") is False:
            decisions[item["asset_id"]]["reasons"].append("quality_review_required")
            continue
        if (semantic.get("confidence", 0) >= 0.7
                and (semantic.get("eye_state") in {"closed", "mixed"} or semantic.get("occlusion") == "major")):
            continue
        ranked.append((index, item))

    # Prefer a strong representative from each scene group before allocating time.
    ranked.sort(key=lambda pair: (-pair[1]["quality"]["score"], pair[0]))
    representatives = []
    groups = {}
    for index, item in ranked:
        group = item.get("duplicate_group") or item["asset_id"]
        if group in groups:
            decisions[item["asset_id"]].update(status="excluded", reasons=["duplicate_alternative"], alternative_to=groups[group])
        else:
            groups[group] = item["asset_id"]
            representatives.append((index, item))

    # Allocate the first pass across different semantic story groups, then fill
    # remaining time with the next-best items. Unknown items remain independent.
    first_by_story, overflow = [], []
    seen_stories = set()
    for pair in representatives:
        item = pair[1]
        story = item.get("story_group") or item["asset_id"]
        if story in seen_stories:
            overflow.append(pair)
        else:
            seen_stories.add(story)
            first_by_story.append(pair)

    selected = []
    remaining = target_seconds
    story_counts = {}
    semantic_repetitions_suppressed = 0
    for index, item in first_by_story + overflow:
        story = item.get("story_group")
        if story and story_counts.get(story, 0) >= 2:
            decisions[item["asset_id"]].update(status="excluded", reasons=["semantic_repetition"])
            semantic_repetitions_suppressed += 1
            continue
        duration = min(max_clip_seconds, item["duration_seconds"] - item.get("recommended_start", 0))
        if item.get("mime_type", "").startswith("image/"):
            duration = min(3.0, duration)
        # Avoid a tiny leftover fragment. Never extend a short source.
        minimum = min(duration, 1.5)
        if remaining + 1e-8 < minimum or len(selected) >= 100:
            decisions[item["asset_id"]].update(status="excluded", reasons=["duration_budget"])
            continue
        duration = round(min(duration, remaining), 2)
        if duration <= 0:
            continue
        start = round(item.get("recommended_start", 0), 2)
        selected.append((index, {**item, "selected_start": start, "selected_duration": duration}))
        reasons = list(decisions[item["asset_id"]]["reasons"]) + ["quality_representative"]
        if item.get("story_group"):
            reasons.append("semantic_story_group")
        decisions[item["asset_id"]].update(status="selected", reasons=list(dict.fromkeys(reasons)),
                                            start=start, duration=duration)
        if story:
            story_counts[story] = story_counts.get(story, 0) + 1
        remaining = round(remaining - duration, 2)
    if selected and all(item.get("capture_time") for _, item in selected):
        selected.sort(key=lambda pair: (pair[1]["capture_time"], pair[0]))
    else:
        selected.sort(key=lambda pair: pair[0])
    for position, (_, item) in enumerate(selected):
        decisions[item["asset_id"]]["story_beat"] = _story_beat(item, position, len(selected))
    semantic = any(item.get("semantic") for item in features)
    return {"method": "local_story_curation_v2" if semantic else "local_technical_quality_v1",
            "target_seconds": target_seconds,
            "duration_seconds": round(target_seconds - remaining, 2),
            "selected": [item for _, item in selected],
            "decisions": [decisions[item["asset_id"]] for item in features],
            "story": {
                "story_groups_covered": len(story_counts),
                "semantic_repetitions_suppressed": semantic_repetitions_suppressed,
                "duplicate_alternatives_suppressed": sum(
                    "duplicate_alternative" in decision.get("reasons", []) for decision in decisions.values()
                ),
                "beats": [decisions[item["asset_id"]]["story_beat"] for _, item in selected],
            },
            "limitations": (["Semantic evidence requires owner review", "Landmark hints are not verified locations"]
                            if semantic else ["No eye-state or landmark model yet", "Chronology follows import order",
                                              "Technical quality is not story relevance"])}


def _story_beat(item: dict, position: int, count: int) -> str:
    if position == 0:
        return "opening"
    if position == count - 1:
        return "closing"
    semantic = item.get("semantic") or {}
    if semantic.get("scene") in {"portrait", "group"} or semantic.get("people_count", 0) > 0:
        return "people"
    if semantic.get("scene") == "activity" or semantic.get("point_of_interest") == "activity":
        return "journey"
    if item.get("editorial_score", 0) >= 0.85:
        return "highlight"
    return "detail"
