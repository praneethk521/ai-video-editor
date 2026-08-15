from __future__ import annotations

from pathlib import Path
from time import perf_counter

import httpx

from app.config import settings
from app.metrics import record_callback, record_render_job
from app.render import VideoRenderer


class RenderCallbackClient:
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_token}"}

    def mark_running(self, render_job_id: str) -> None:
        self._post(f"/internal/render-jobs/{render_job_id}/running", operation="running")

    def complete(self, render_job_id: str, payload: dict) -> None:
        self._post(f"/internal/render-jobs/{render_job_id}/complete", operation="complete", json=payload)

    def fail(self, render_job_id: str, error_message: str) -> None:
        self._post(
            f"/internal/render-jobs/{render_job_id}/fail",
            operation="fail",
            json={"error_message": error_message[:2000]},
        )

    def _post(self, path: str, *, operation: str, json: dict | None = None) -> None:
        try:
            with httpx.Client(base_url=self.base_url, timeout=30) as client:
                response = client.post(path, headers=self.headers, json=json)
                response.raise_for_status()
        except Exception:
            record_callback(operation=operation, outcome="failed")
            raise
        record_callback(operation=operation, outcome="succeeded")


def render_timeline_job(render_job_id: str, plan: dict, dry_run: bool | None = None) -> dict:
    callback = RenderCallbackClient(settings.api_base_url, settings.api_token)
    dry_run = settings.render_dry_run if dry_run is None else dry_run
    variant = str(plan.get("variant") or "unknown")
    started_at = perf_counter()
    try:
        callback.mark_running(render_job_id)
        payload = render_timeline(plan, dry_run=dry_run)
        callback.complete(render_job_id, payload)
        record_render_job(variant=variant, outcome="succeeded", elapsed_seconds=perf_counter() - started_at)
        return payload
    except Exception as exc:
        record_render_job(variant=variant, outcome="failed", elapsed_seconds=perf_counter() - started_at)
        try:
            callback.fail(render_job_id, str(exc))
        except Exception:
            pass
        raise


def render_timeline(plan: dict, dry_run: bool = True) -> dict:
    renderer = VideoRenderer(Path(settings.temp_root) / "outputs")
    result = renderer.render(plan, dry_run=dry_run)
    output_path = Path(result.output_path)
    return {
        "variant": result.variant,
        "private_locator": f"file://private/{output_path.parent.name}/{output_path.name}",
        "width": result.width,
        "height": result.height,
        "duration_seconds": result.duration_seconds,
        "file_size_bytes": output_path.stat().st_size,
        "upload_package": result.upload_package,
        "validation": result.validation,
    }
