from __future__ import annotations

import array
import hashlib
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from app import render
from app.render import VideoRenderer
from app.validation import OutputValidationError, detect_black_frames
from video_shared.timeline import AssetSummary, build_timeline_plan


def test_still_images_loop_after_scaling(tmp_path, monkeypatch):
    root = tmp_path / "sources"
    source = root / "project-test"
    source.mkdir(parents=True)
    photo = source / "large-photo.jpg"
    photo.write_bytes(b"fixture")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"rendered")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(render, "settings", replace(render.settings, media_source_root=str(root)))
    monkeypatch.setattr(render, "probe_media", lambda *_args: {
        "mime_type": "image/jpeg", "duration_seconds": 0, "has_audio": False,
    })
    monkeypatch.setattr(render.subprocess, "run", fake_run)
    monkeypatch.setattr(render, "validate_output_file", lambda *_args, **_kwargs: {"status": "passed"})
    plan = build_timeline_plan("project-test", [AssetSummary("photo", 3)], "youtube_16x9")
    VideoRenderer(tmp_path / "outputs").render(plan, sources={"photo": {
        "relative_path": "project-test/large-photo.jpg",
        "sha256": hashlib.sha256(photo.read_bytes()).hexdigest(),
    }})

    segment_command = commands[0]
    assert "-loop" not in segment_command
    assert "loop=loop=-1:size=1:start=0" in segment_command[segment_command.index("-vf") + 1]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="real renderer test needs FFmpeg")
@pytest.mark.parametrize("variant", ["youtube_16x9", "shorts_9x16"])
def test_actual_images_video_and_audio_survive_render(tmp_path, monkeypatch, variant):
    root = tmp_path / "sources"
    source = root / "project-test"
    source.mkdir(parents=True)

    def ffmpeg(*args):
        return subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True, timeout=60).stdout

    photo = source / "photo.jpg"
    video = source / "clip.mp4"
    soundtrack = source / "soundtrack.wav"
    ffmpeg("-f", "lavfi", "-i", "color=red:s=160x90", "-frames:v", "1", str(photo))
    ffmpeg("-f", "lavfi", "-i", "color=blue:s=160x90:r=30:d=0.6", "-f", "lavfi", "-i",
           "sine=frequency=440:duration=0.6", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video))
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=0.7", str(soundtrack))
    sources = {name: {"relative_path": f"project-test/{path.name}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for name, path in (("photo", photo), ("video", video), ("soundtrack", soundtrack))}
    monkeypatch.setattr(render, "settings", replace(render.settings, media_source_root=str(root)))
    plan = build_timeline_plan("project-test", [AssetSummary("photo", 3), AssetSummary("video", 0.6)], variant)
    plan["soundtrack"] = {"mode": "manual", "asset_id": "soundtrack", "filename": "soundtrack.wav",
                            "music_gain_db": -13, "original_gain_db": -3}
    plan["tracks"].append({"type": "audio", "clips": [{"asset_id": "soundtrack", "start": 0,
                                                          "end": 3.6, "timeline_start": 0,
                                                          "effect": "soundtrack"}]})
    result = VideoRenderer(tmp_path / "outputs").render(plan, sources=sources)
    assert result.validation["status"] == "passed"
    assert result.validation["signals"]["black_frames"]["detected"] is False
    assert abs(result.validation["ffprobe"]["duration_seconds"] - 3.6) < 0.15

    def pixel(at):
        return ffmpeg("-ss", str(at), "-i", result.output_path, "-vf", "crop=2:2:iw/2:ih/2,scale=1:1",
                      "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1")

    red, blue = pixel(1), pixel(3.3)
    assert red[0] > 180 and red[2] < 50
    assert blue[2] > 180 and blue[0] < 50
    sound = ffmpeg("-ss", "3.2", "-i", result.output_path, "-t", "0.2", "-vn", "-ac", "1", "-f", "s16le", "pipe:1")
    samples = array.array("h", sound)
    assert max(abs(sample) for sample in samples) > 500
    photo_sound = ffmpeg("-ss", "1", "-i", result.output_path, "-t", "0.2", "-vn", "-ac", "1", "-f", "s16le", "pipe:1")
    assert max(abs(sample) for sample in array.array("h", photo_sound)) > 500
    assert not list((tmp_path / "outputs" / "project-test").glob("segments-*"))


def test_missing_and_foreign_sources_fail_before_ffmpeg(tmp_path):
    plan = build_timeline_plan("project-test", [AssetSummary("photo", 3)], "youtube_16x9")
    renderer = VideoRenderer(tmp_path / "outputs")
    with pytest.raises(ValueError, match="manifest"):
        renderer.render(plan)
    with pytest.raises(ValueError, match="missing or outside"):
        renderer.render(plan, sources={"photo": {"relative_path": "../other-project/file", "sha256": "fake"}})
    assert not list((tmp_path / "outputs").rglob("*.mp4"))


def test_invalid_project_identifier_rejected(tmp_path):
    plan = build_timeline_plan("../escape", [AssetSummary("photo", 3)], "youtube_16x9")
    with pytest.raises(ValueError, match="storage identifier"):
        VideoRenderer(tmp_path).render(plan)


def test_short_video_not_extended_and_input_overflow_rejected():
    plan = build_timeline_plan("project-test", [AssetSummary("short", 0.2)], "shorts_9x16")
    assert plan["tracks"][0]["clips"][0]["end"] == 0.2
    with pytest.raises(ValueError, match="at most 12"):
        build_timeline_plan("project-test", [AssetSummary(str(i), 3) for i in range(13)], "shorts_9x16")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="real renderer test needs FFmpeg")
def test_truly_black_media_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / "sources" / "black-project"
    source.mkdir(parents=True)
    photo = source / "black.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=160x90",
                    "-frames:v", "1", str(photo)], check=True, capture_output=True)
    monkeypatch.setattr(render, "settings", replace(render.settings, media_source_root=str(source.parent)))
    plan = build_timeline_plan("black-project", [AssetSummary("black", 3)], "youtube_16x9")
    with pytest.raises(OutputValidationError):
        VideoRenderer(tmp_path / "outputs").render(plan, sources={"black": {
            "relative_path": "black-project/black.jpg", "sha256": hashlib.sha256(photo.read_bytes()).hexdigest()}})
    assert not list((tmp_path / "outputs").rglob("*.mp4"))


def test_failed_decode_is_not_a_pass(tmp_path, monkeypatch):
    monkeypatch.setattr("app.validation.subprocess.run", lambda *args, **kwargs: subprocess.CompletedProcess([], 1, stderr="invalid data"))
    assert detect_black_frames(tmp_path / "bad.mp4")["status"] == "failed"
