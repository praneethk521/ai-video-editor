from __future__ import annotations

import subprocess
import hashlib
import math
import tempfile
import time
from uuid import uuid4
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.music import generate_original_score
from app.timeline import validate_timeline
from app.validation import skipped_validation, validate_output_file
from video_shared.media import probe_media, safe_component, source_path


@dataclass(frozen=True)
class RenderResult:
    variant: str
    output_path: str
    width: int
    height: int
    duration_seconds: float
    upload_package: dict
    validation: dict


class VideoRenderer:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.output_root.mkdir(parents=True, exist_ok=True)

    def render(self, plan: dict, dry_run: bool = False, sources: dict | None = None) -> RenderResult:
        plan = validate_timeline(plan)
        project_id = safe_component(plan["project_id"])
        variant = plan["variant"]
        export = plan["export"]
        duration = self._duration(plan)
        filename = f"{variant}.mp4" if dry_run else f"{variant}-{uuid4().hex}.mp4"
        output_path = self.output_root / project_id / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if dry_run:
            output_path.write_bytes(b"private placeholder mp4 for local integration tests\n")
            validation = skipped_validation("dry_run")
        else:
            try:
                self._render_sources(output_path, plan, sources or {})
                validation = validate_output_file(
                    output_path, expected_width=export["width"], expected_height=export["height"],
                    expected_duration_seconds=duration, delivery_target=settings.output_storage_provider,
                    require_embedded_subtitles=settings.require_embedded_subtitles,
                    fail_on_black_frames=True,
                )
            except Exception:
                output_path.unlink(missing_ok=True)
                raise

        return RenderResult(
            variant=variant,
            output_path=str(output_path),
            width=export["width"],
            height=export["height"],
            duration_seconds=duration,
            validation=validation,
            upload_package={
                "title_suggestions": plan.get("strategy", {}).get("title_ideas", []),
                "description": plan.get("strategy", {}).get("description", ""),
                "hashtags": plan.get("strategy", {}).get("hashtags", []),
                "chapters": self._chapters(plan) if variant == "youtube_16x9" else [],
                "manual_upload_only": True,
                "delivery_target": settings.output_storage_provider,
                "delivery_status": "private_staging",
                "soundtrack": plan.get("soundtrack") or {"mode": "none", "asset_id": None},
            },
        )

    def _render_sources(self, output_path: Path, plan: dict, sources: dict) -> None:
        tracks = plan["tracks"]
        video_tracks = [track for track in tracks if track["type"] == "video"]
        audio_tracks = [track for track in tracks if track["type"] == "audio"]
        if len(video_tracks) != 1 or len(audio_tracks) > 1 or len(video_tracks) + len(audio_tracks) != len(tracks):
            raise ValueError("montage rendering requires one video track and at most one soundtrack")
        clips = video_tracks[0]["clips"]
        export = plan["export"]
        width, height, fps = export["width"], export["height"], export["fps"]
        if not 1 <= len(clips) <= 100 or (width, height) not in {(1920, 1080), (1080, 1920)} or fps != 30:
            raise ValueError("unsupported montage export or clip count")
        resolved = []
        cursor = 0.0
        for clip in clips:
            duration = clip["end"] - clip["start"]
            if not math.isfinite(duration) or duration <= 0 or abs(clip["timeline_start"] - cursor) > 0.01:
                raise ValueError("clips must be positive and contiguous")
            if clip.get("effect") not in {None, "cut"} or clip.get("caption"):
                raise ValueError("effects and captions are not supported by the montage renderer")
            if clip.get("crop_strategy") not in {None, "center"}:
                raise ValueError("only aspect-preserving montage fit is supported")
            source = sources.get(clip["asset_id"])
            if not source:
                raise ValueError("source manifest is missing a timeline asset")
            path = source_path(Path(settings.media_source_root), plan["project_id"], source["relative_path"])
            with path.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            if checksum != source["sha256"]:
                raise ValueError("source changed after validation")
            metadata = probe_media(path, settings.ffprobe_path)
            still = metadata["mime_type"].startswith("image/")
            if not still and clip["end"] > metadata["duration_seconds"] + 0.01:
                raise ValueError("clip exceeds source duration")
            resolved.append((clip, path, metadata, still, duration))
            cursor += duration
        if cursor > min(export.get("max_duration_seconds", 900), 900):
            raise ValueError("timeline exceeds export duration limit")
        soundtrack = self._resolve_soundtrack(plan, audio_tracks, sources, cursor)
        deadline = time.monotonic() + settings.max_job_seconds

        def run(command: list[str]) -> None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("render deadline exceeded")
            subprocess.run([settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *command],
                           check=True, capture_output=True, timeout=remaining)

        with tempfile.TemporaryDirectory(prefix="segments-", dir=output_path.parent) as temporary:
            directory = Path(temporary)
            segments = []
            for index, (clip, path, metadata, still, duration) in enumerate(resolved):
                segment = directory / f"segment-{index}.mp4"
                args = ["-protocol_whitelist", "file,pipe", "-threads", "2"]
                if not still:
                    args += ["-ss", str(clip["start"])]
                args += ["-i", str(path)]
                has_audio = not still and metadata["has_audio"]
                if not has_audio:
                    args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                still_loop = ",loop=loop=-1:size=1:start=0" if still else ""
                fit = f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:out_range=tv:out_color_matrix=bt709,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1{still_loop},fps={fps},format=yuv420p,setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709"
                args += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                         "-vf", fit, "-af", "aresample=48000,apad", "-t", str(duration),
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-threads", "2",
                         "-filter_threads", "1", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
                         "-map_metadata", "-1", str(segment)]
                run(args)
                segments.append(segment)
            concat = directory / "concat.txt"
            concat.write_text("".join(f"file '{segment.name}'\n" for segment in segments))
            assembled = directory / "assembled.mp4"
            run(["-f", "concat", "-safe", "1", "-i", str(concat), "-c", "copy", str(assembled)])
            soundtrack_settings = plan.get("soundtrack") or {}
            include_original = bool(soundtrack_settings.get("include_original_audio", False))
            if soundtrack is None:
                if include_original:
                    assembled.replace(output_path)
                else:
                    run(["-i", str(assembled), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                         "-map", "0:v:0", "-map", "1:a:0", "-t", str(cursor), "-c:v", "copy",
                         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                         "-map_metadata", "-1", str(output_path)])
            else:
                music_gain = float(soundtrack_settings.get("music_gain_db", -13))
                original_gain = float(soundtrack_settings.get("original_gain_db", -3))
                fade_out = max(0, cursor - 1)
                if isinstance(soundtrack, str):
                    generated_score = directory / "original-score.wav"
                    generate_original_score(generated_score, soundtrack, cursor)
                    music_input = ["-i", str(generated_score)]
                else:
                    clip, path = soundtrack
                    music_input = ["-stream_loop", "-1", "-ss", str(clip["start"]), "-i", str(path)]
                music_filter = (
                    f"[1:a]volume={music_gain}dB,afade=t=in:st=0:d=1,"
                    f"afade=t=out:st={fade_out}:d=1[music]"
                )
                if include_original:
                    mix = (
                        f"[0:a]volume={original_gain}dB[original];{music_filter};"
                        "[original][music]amix=inputs=2:duration=first:dropout_transition=2,"
                        "loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
                    )
                else:
                    mix = f"{music_filter};[music]loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
                run(["-i", str(assembled), *music_input,
                     "-filter_complex", mix, "-map", "0:v:0", "-map", "[aout]", "-t", str(cursor),
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                     "-movflags", "+faststart", "-map_metadata", "-1", str(output_path)])

    @staticmethod
    def _resolve_soundtrack(plan: dict, audio_tracks: list[dict], sources: dict, duration: float):
        configured = plan.get("soundtrack") or {}
        if configured.get("mode") == "generated":
            preset = configured.get("generated_preset")
            if audio_tracks or configured.get("asset_id") is not None or preset not in {
                "calm_cinematic", "bright_journey", "warm_memories"
            }:
                raise ValueError("generated soundtrack metadata is invalid")
            return preset
        if not audio_tracks:
            if configured.get("mode") not in {None, "none"}:
                raise ValueError("soundtrack selection is missing its audio track")
            return None
        clips = audio_tracks[0].get("clips") or []
        if len(clips) != 1:
            raise ValueError("soundtrack requires exactly one audio clip")
        clip = clips[0]
        if (clip.get("effect") != "soundtrack" or clip.get("timeline_start") != 0
                or clip.get("start", -1) < 0 or abs(clip.get("end", 0) - duration) > 0.01):
            raise ValueError("soundtrack clip must span the visual timeline")
        if configured.get("asset_id") != clip.get("asset_id") or configured.get("mode") not in {"auto", "latest", "manual"}:
            raise ValueError("soundtrack metadata does not match its audio track")
        source = sources.get(clip["asset_id"])
        if not source:
            raise ValueError("source manifest is missing the soundtrack asset")
        path = source_path(Path(settings.media_source_root), plan["project_id"], source["relative_path"])
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if checksum != source["sha256"]:
            raise ValueError("soundtrack source changed after validation")
        metadata = probe_media(path, settings.ffprobe_path)
        if not metadata["mime_type"].startswith("audio/"):
            raise ValueError("soundtrack source must be an audio file")
        return clip, path

    @staticmethod
    def _duration(plan: dict) -> float:
        max_end = 0.0
        for track in plan["tracks"]:
            if track["type"] != "video":
                continue
            for clip in track["clips"]:
                max_end = max(max_end, clip["timeline_start"] + (clip["end"] - clip["start"]))
        return round(max_end, 2)

    @staticmethod
    def _chapters(plan: dict) -> list[dict]:
        chapters = []
        for index, clip in enumerate(plan["tracks"][0]["clips"], start=1):
            chapters.append({"time": clip["timeline_start"], "title": f"Moment {index}"})
        return chapters

    @staticmethod
    def _caption_count(plan: dict) -> int:
        count = 0
        for track in plan["tracks"]:
            for clip in track["clips"]:
                if clip.get("caption"):
                    count += 1
        return count
