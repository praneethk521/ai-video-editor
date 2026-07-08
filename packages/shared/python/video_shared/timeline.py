from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Variant = Literal["youtube_16x9", "shorts_9x16"]


@dataclass(frozen=True)
class AssetSummary:
    asset_id: str
    duration_seconds: float
    orientation: str = "landscape"
    highlight_score: float = 0.5
    scene_count: int = 1
    subject_presence: str = "unknown"
    audio_quality: str = "unknown"
    tags: tuple[str, ...] = ()


def build_timeline_plan(project_id: str, assets: list[AssetSummary], variant: Variant) -> dict:
    if not assets:
        raise ValueError("at least one asset is required to build a timeline")

    ranked = sorted(assets, key=lambda asset: asset.highlight_score, reverse=True)
    width, height = (1920, 1080) if variant == "youtube_16x9" else (1080, 1920)
    max_clip = 8.0 if variant == "youtube_16x9" else 3.0
    top_tags = sorted({tag for asset in ranked[:5] for tag in asset.tags})
    primary_focus = _primary_focus(ranked)
    pacing = _pacing(variant, ranked)
    timeline_start = 0.0
    clips = []

    for asset in ranked[:12]:
        clip_len = min(max_clip, max(1.5, asset.duration_seconds))
        crop_strategy = "face_subject" if asset.subject_presence != "unknown" else "center"
        if variant == "shorts_9x16" and asset.orientation == "landscape":
            crop_strategy = "blur_background"
        clips.append(
            {
                "asset_id": asset.asset_id,
                "start": 0,
                "end": round(clip_len, 2),
                "timeline_start": round(timeline_start, 2),
                "effect": _effect_for_asset(variant, asset),
                "caption": _caption_for_asset(asset),
                "crop_strategy": crop_strategy,
            }
        )
        timeline_start += clip_len

    return {
        "project_id": project_id,
        "variant": variant,
        "version": 1,
        "confidence_score": round(min(0.95, 0.55 + len(clips) * 0.03), 2),
        "strategy": {
            "hook": f"Open with the highest-scoring {primary_focus} moment in the first three seconds.",
            "pacing": pacing,
            "title_ideas": _title_ideas(primary_focus, variant),
            "description": _description(primary_focus, top_tags),
            "hashtags": _hashtags(top_tags),
        },
        "tracks": [{"type": "video", "clips": clips}],
        "export": {
            "width": width,
            "height": height,
            "fps": 30,
            "format": "mp4",
            "audio_lufs": -14,
            "max_duration_seconds": 900 if variant == "youtube_16x9" else 60,
        },
    }


def _primary_focus(assets: list[AssetSummary]) -> str:
    if not assets:
        return "visual"
    tags = [tag for asset in assets[:5] for tag in asset.tags if tag != "general"]
    if not tags:
        return "visual"
    for priority_tag in ("talking_head", "hook", "hero", "highlight", "demo", "screen_recording", "interview"):
        if priority_tag in tags:
            return priority_tag.replace("_", " ")
    return tags[0].replace("_", " ")


def _pacing(variant: Variant, assets: list[AssetSummary]) -> str:
    if variant == "shorts_9x16":
        if any(asset.subject_presence != "unknown" for asset in assets):
            return "fast cuts anchored on subject-forward moments"
        return "fast cuts with pattern interrupts"
    if any(asset.audio_quality == "needs_review" for asset in assets):
        return "calm visual-led pacing with conservative audio moments"
    return "calm retention-driven pacing"


def _effect_for_asset(variant: Variant, asset: AssetSummary) -> str:
    if asset.scene_count >= 4:
        return "match_cut"
    if asset.subject_presence != "unknown":
        return "subject_push" if variant == "shorts_9x16" else "subtle_zoom"
    return "subtle_zoom" if variant == "youtube_16x9" else "quick_push"


def _caption_for_asset(asset: AssetSummary) -> str:
    if asset.subject_presence != "unknown":
        return "Keep the subject framed and caption the spoken highlight."
    if "screen_recording" in asset.tags:
        return "Call out the key on-screen action."
    if "still" in asset.tags:
        return "Use as a visual beat with concise context."
    return "Highlight the strongest visual moment."


def _title_ideas(primary_focus: str, variant: Variant) -> list[str]:
    if variant == "shorts_9x16":
        return [f"Quick {primary_focus} highlight", "Best moment in under a minute"]
    return [f"A polished {primary_focus} edit", "Best moments from this project"]


def _description(primary_focus: str, top_tags: list[str]) -> str:
    tag_text = ", ".join(tag.replace("_", " ") for tag in top_tags[:4]) or "private media"
    return f"Private manual-upload package focused on {primary_focus}; analysis tags: {tag_text}."


def _hashtags(top_tags: list[str]) -> list[str]:
    hashtags = ["#video", "#edit", "#private"]
    for tag in top_tags[:3]:
        normalized = "".join(part.capitalize() for part in tag.split("_"))
        hashtags.append(f"#{normalized}")
    return list(dict.fromkeys(hashtags))
