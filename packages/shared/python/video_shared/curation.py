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
        score = quality.get("score", 0)
        duration = item.get("duration_seconds", 0)
        start = item.get("recommended_start", 0)
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (score, duration, start)):
            raise ValueError("candidate evidence must be finite")
        if not 0 <= score <= 1 or duration <= 0 or not 0 <= start < duration:
            raise ValueError("invalid candidate evidence")
        reasons = list(quality.get("flags") or [])
        decisions[item["asset_id"]] = {"asset_id": item["asset_id"], "status": "review",
                                       "reasons": reasons, "score": score}
        if quality.get("usable") is False:
            decisions[item["asset_id"]]["reasons"].append("quality_review_required")
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

    selected = []
    remaining = target_seconds
    for index, item in representatives:
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
        decisions[item["asset_id"]].update(status="selected", reasons=["quality_representative"], start=start, duration=duration)
        remaining = round(remaining - duration, 2)
    selected.sort(key=lambda pair: pair[0])
    return {"method": "local_technical_quality_v1", "target_seconds": target_seconds,
            "duration_seconds": round(target_seconds - remaining, 2),
            "selected": [item for _, item in selected],
            "decisions": [decisions[item["asset_id"]] for item in features],
            "limitations": ["No eye-state or landmark model yet", "Chronology follows import order", "Technical quality is not story relevance"]}
