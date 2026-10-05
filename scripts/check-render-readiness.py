"""Exercise the current renderer with synthetic fixtures; never call cloud services.

Run with worker dependencies plus FFmpeg/ffprobe. See docs/TRIP_VIDEO_READINESS.md.
Exit 2 means the renderer has not met even the basic non-placeholder check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/worker"))
sys.path.insert(0, str(ROOT / "packages/shared/python"))

from app.config import settings  # noqa: E402
from app import render as render_module  # noqa: E402
from app.render import VideoRenderer  # noqa: E402
from app.validation import OutputValidationError  # noqa: E402
from video_shared.timeline import AssetSummary, build_timeline_plan  # noqa: E402


def ffmpeg(*args: str) -> None:
    subprocess.run(
        [settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        timeout=120,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    # Refuse to overwrite previous evidence or any user files.
    root.mkdir(parents=True, exist_ok=False)
    source = root / "source" / "synthetic-trip"
    source.mkdir(parents=True)
    render_module.settings = replace(settings, media_source_root=str(root / "source"))
    assets = []
    manifest = []
    for index, color in enumerate(("red", "green", "blue", "yellow", "magenta"), 1):
        filename = source / f"photo-{index}.png"
        ffmpeg("-f", "lavfi", "-i", f"color=c={color}:s=640x360", "-frames:v", "1", str(filename))
        asset_id = f"synthetic-photo-{index}"
        manifest.append({"asset_id": asset_id, "path": str(filename), "mime_type": "image/png"})
        assets.append(AssetSummary(asset_id=asset_id, duration_seconds=1.5, tags=("still",)))
    clip = source / "sample-video.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip),
    )
    manifest.append({"asset_id": "synthetic-video", "path": str(clip), "mime_type": "video/mp4"})
    assets.append(AssetSummary(asset_id="synthetic-video", duration_seconds=2))
    (root / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    sources = {entry["asset_id"]: {
        "relative_path": f"synthetic-trip/{Path(entry['path']).name}",
        "sha256": hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest(),
    } for entry in manifest}

    report = {
        "scope": "Renderer diagnostic, not an end-to-end application or Drive demo",
        "source_count": len(manifest),
        "source_manifest_consumed": True,
        "runs": [],
    }
    for variant in ("youtube_16x9", "shorts_9x16"):
        plan = build_timeline_plan("synthetic-trip", assets, variant)
        (root / f"{variant}-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
        for dry_run in (True, False):
            mode = "dry-run" if dry_run else "ffmpeg"
            renderer = VideoRenderer(root / mode)
            try:
                result = renderer.render(plan, dry_run=dry_run, sources=sources)
                evidence = asdict(result)
            except OutputValidationError as exc:
                evidence = {"validation": exc.validation, "error": str(exc)}
            evidence["mode"] = mode
            evidence["variant"] = variant
            path = Path(evidence.get("output_path", root / mode / "synthetic-trip" / f"{variant}.mp4"))
            probe = subprocess.run(
                [settings.ffprobe_path, "-v", "error", "-show_format", str(path)],
                capture_output=True, text=True, timeout=30,
            )
            evidence["playable_container"] = probe.returncode == 0
            evidence["probe_error"] = probe.stderr.strip()
            report["runs"].append(evidence)

    real_runs = [run for run in report["runs"] if run["mode"] == "ffmpeg"]
    basic_check = all(
        run["playable_container"]
        and run["validation"].get("status") == "passed"
        and run["validation"].get("signals", {}).get("black_frames", {}).get("status") == "passed"
        for run in real_runs
    )
    report["basic_non_placeholder_check_passed"] = basic_check
    report["trip_workflow_verified"] = False
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if basic_check else 2


if __name__ == "__main__":
    raise SystemExit(main())
