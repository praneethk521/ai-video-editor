from __future__ import annotations

from pathlib import Path

from app.jobs import render_timeline
from app.render import VideoRenderer
from app.validation import parse_blackdetect_output, summarize_ffprobe


def test_renderer_validates_and_creates_private_output(tmp_path: Path):
    plan = {
        "project_id": "project-1",
        "variant": "shorts_9x16",
        "version": 1,
        "confidence_score": 0.77,
        "strategy": {
            "title_ideas": ["A short"],
            "description": "Manual upload package",
            "hashtags": ["#private"],
        },
        "tracks": [
            {
                "type": "video",
                "clips": [
                    {
                        "asset_id": "asset-1",
                        "start": 0,
                        "end": 2.5,
                        "timeline_start": 0,
                        "crop_strategy": "blur_background",
                    }
                ],
            }
        ],
        "export": {"width": 1080, "height": 1920, "fps": 30, "format": "mp4"},
    }

    result = VideoRenderer(tmp_path).render(plan)
    assert result.variant == "shorts_9x16"
    assert result.width == 1080
    assert Path(result.output_path).exists()
    assert result.upload_package["manual_upload_only"] is True
    assert result.upload_package["delivery_target"] == "drive"
    assert result.validation["status"] == "skipped"


def test_render_timeline_returns_private_output_metadata():
    plan = {
        "project_id": "project-1",
        "variant": "youtube_16x9",
        "version": 1,
        "confidence_score": 0.77,
        "tracks": [
            {
                "type": "video",
                "clips": [
                    {
                        "asset_id": "asset-1",
                        "start": 0,
                        "end": 2.5,
                        "timeline_start": 0,
                    }
                ],
            }
        ],
        "export": {"width": 1920, "height": 1080, "fps": 30, "format": "mp4"},
    }

    result = render_timeline(plan)
    assert result["variant"] == "youtube_16x9"
    assert result["private_locator"] == "file://private/project-1/youtube_16x9.mp4"
    assert result["file_size_bytes"] > 0
    assert result["upload_package"]["manual_upload_only"] is True
    assert result["upload_package"]["delivery_status"] == "private_staging"
    assert result["validation"]["status"] == "skipped"


def test_summarizes_ffprobe_output():
    summary = summarize_ffprobe(
        {
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080},
                {"codec_type": "audio"},
                {"codec_type": "subtitle"},
            ],
            "format": {"duration": "2.560000", "format_name": "mov,mp4,m4a,3gp,3g2,mj2", "size": "4096"},
        }
    )

    assert summary == {
        "has_video": True,
        "has_audio": True,
        "has_subtitles": True,
        "width": 1920,
        "height": 1080,
        "duration_seconds": 2.56,
        "container": "mov,mp4,m4a,3gp,3g2,mj2",
        "size_bytes": 4096,
    }


def test_parses_blackdetect_output():
    signal = parse_blackdetect_output(
        "[blackdetect @ 0x123] black_start:0 black_end:1.2 black_duration:1.2\n"
        "[blackdetect @ 0x123] black_start:3 black_end:3.5 black_duration:0.5"
    )

    assert signal == {
        "status": "warning",
        "detected": True,
        "segments": [
            {"start": 0.0, "end": 1.2, "duration": 1.2},
            {"start": 3.0, "end": 3.5, "duration": 0.5},
        ],
        "total_duration_seconds": 1.7,
    }
