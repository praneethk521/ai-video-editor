from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.timeline import validate_timeline
from app.validation import skipped_validation, validate_output_file


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

    def render(self, plan: dict, dry_run: bool = True) -> RenderResult:
        plan = validate_timeline(plan)
        project_id = plan["project_id"]
        variant = plan["variant"]
        export = plan["export"]
        duration = self._duration(plan)
        output_path = self.output_root / project_id / f"{variant}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if dry_run:
            output_path.write_bytes(b"private placeholder mp4 for local integration tests\n")
            validation = skipped_validation("dry_run")
        else:
            self._render_placeholder_with_ffmpeg(output_path, export, duration)
            validation = validate_output_file(
                output_path,
                expected_width=export["width"],
                expected_height=export["height"],
                expected_duration_seconds=duration,
            )

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
            },
        )

    def _render_placeholder_with_ffmpeg(self, output_path: Path, export: dict, duration: float) -> None:
        command = [
            settings.ffmpeg_path,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={export['width']}x{export['height']}:d={max(duration, 1)}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate=48000:d={max(duration, 1)}",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output_path),
        ]
        subprocess.run(command, check=True, timeout=settings.max_job_seconds)

    @staticmethod
    def _duration(plan: dict) -> float:
        max_end = 0.0
        for track in plan["tracks"]:
            for clip in track["clips"]:
                max_end = max(max_end, clip["timeline_start"] + (clip["end"] - clip["start"]))
        return round(max_end, 2)

    @staticmethod
    def _chapters(plan: dict) -> list[dict]:
        chapters = []
        for index, clip in enumerate(plan["tracks"][0]["clips"], start=1):
            chapters.append({"time": clip["timeline_start"], "title": f"Moment {index}"})
        return chapters
