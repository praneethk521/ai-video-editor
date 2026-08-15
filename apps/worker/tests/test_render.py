from __future__ import annotations

from pathlib import Path

import pytest
from prometheus_client import generate_latest

from app import jobs as worker_jobs
from app.config import WorkerSettings
from app.jobs import render_timeline
from app.render import VideoRenderer
from app.tracing import normalized_variant, parse_exporter_headers
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


def test_render_job_records_worker_metrics(monkeypatch):
    callback_events = []

    class FakeCallback:
        def mark_running(self, render_job_id: str) -> None:
            callback_events.append(("running", render_job_id))

        def complete(self, render_job_id: str, payload: dict) -> None:
            callback_events.append(("complete", render_job_id))

        def fail(self, render_job_id: str, error_message: str) -> None:
            callback_events.append(("fail", render_job_id))

    monkeypatch.setattr(worker_jobs, "RenderCallbackClient", lambda base_url, api_token: FakeCallback())
    monkeypatch.setattr(
        worker_jobs,
        "render_timeline",
        lambda plan, dry_run: {"variant": plan["variant"], "validation": {"status": "passed"}},
    )

    result = worker_jobs.render_timeline_job("render-1", {"variant": "youtube_16x9"}, dry_run=True)
    metrics = generate_latest().decode("utf-8")

    assert result["variant"] == "youtube_16x9"
    assert callback_events == [("running", "render-1"), ("complete", "render-1")]
    assert "ai_video_editor_worker_render_jobs_total" in metrics
    assert 'variant="youtube_16x9"' in metrics
    assert 'outcome="succeeded"' in metrics


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


def test_worker_trace_configuration_uses_bounded_attributes():
    assert parse_exporter_headers("authorization=Bearer%20secret") == {
        "authorization": "Bearer secret"
    }
    assert normalized_variant("untrusted-value") == "unknown"
    with pytest.raises(ValueError, match="OTEL_TRACE_SAMPLE_RATIO"):
        WorkerSettings(otel_trace_sample_ratio=1.1)
