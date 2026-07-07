from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.render import VideoRenderer


def render_timeline_job(plan: dict, dry_run: bool = True) -> dict:
    renderer = VideoRenderer(Path(settings.temp_root) / "outputs")
    result = renderer.render(plan, dry_run=dry_run)
    return {
        "variant": result.variant,
        "private_locator": f"file://private/{Path(result.output_path).name}",
        "width": result.width,
        "height": result.height,
        "duration_seconds": result.duration_seconds,
        "upload_package": result.upload_package,
    }

