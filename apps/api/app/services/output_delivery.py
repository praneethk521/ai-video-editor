from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.entities import OutputVideo


def add_shared_path() -> None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "packages" / "shared" / "python"
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.append(str(candidate))
            return
    container_candidate = Path("/packages/shared/python")
    if container_candidate.exists() and str(container_candidate) not in sys.path:
        sys.path.append(str(container_candidate))


add_shared_path()

from video_shared import validate_private_locator  # noqa: E402


ALLOWED_DELIVERY_TARGETS = {"drive", "s3", "local_private"}
ALLOWED_DELIVERY_STATUSES = {"private_staging", "pending_private_delivery", "delivered", "failed"}


def record_output_delivery(
    db: Session,
    *,
    output_video_id: str,
    target: str,
    status: str,
    delivered_locator: str | None,
    details: dict,
) -> OutputVideo:
    output = db.get(OutputVideo, output_video_id)
    if output is None:
        raise ValueError("output video not found")
    if target not in ALLOWED_DELIVERY_TARGETS:
        raise ValueError("unsupported output delivery target")
    if status not in ALLOWED_DELIVERY_STATUSES:
        raise ValueError("unsupported output delivery status")
    if status == "delivered" and not delivered_locator:
        raise ValueError("delivered outputs require a private delivered locator")

    output.delivery_target = target
    output.delivery_status = status
    if delivered_locator is not None:
        output.delivered_locator = validate_private_locator(delivered_locator)
    output.delivery_json = {
        **(output.delivery_json or {}),
        "target": target,
        "status": status,
        "details": details,
    }
    return output
