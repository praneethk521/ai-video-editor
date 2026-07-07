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


def build_timeline_plan(project_id: str, assets: list[AssetSummary], variant: Variant) -> dict:
    if not assets:
        raise ValueError("at least one asset is required to build a timeline")

    ranked = sorted(assets, key=lambda asset: asset.highlight_score, reverse=True)
    width, height = (1920, 1080) if variant == "youtube_16x9" else (1080, 1920)
    max_clip = 8.0 if variant == "youtube_16x9" else 3.0
    pacing = "calm retention-driven pacing" if variant == "youtube_16x9" else "fast cuts with pattern interrupts"
    timeline_start = 0.0
    clips = []

    for asset in ranked[:12]:
        clip_len = min(max_clip, max(1.5, asset.duration_seconds))
        crop_strategy = "face_subject" if variant == "shorts_9x16" else "center"
        if variant == "shorts_9x16" and asset.orientation == "landscape":
            crop_strategy = "blur_background"
        clips.append(
            {
                "asset_id": asset.asset_id,
                "start": 0,
                "end": round(clip_len, 2),
                "timeline_start": round(timeline_start, 2),
                "effect": "subtle_zoom" if variant == "youtube_16x9" else "quick_push",
                "caption": "Auto-caption placeholder",
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
            "hook": "Open with the strongest visual moment in the first three seconds.",
            "pacing": pacing,
            "title_ideas": ["A polished private edit", "Best moments from this project"],
            "description": "Private upload package generated for manual publishing.",
            "hashtags": ["#video", "#edit", "#private"],
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

