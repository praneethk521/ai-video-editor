from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import AuditLog

SENSITIVE_METADATA_KEYS = {"folder_url", "access_token", "refresh_token", "private_locator", "media_url"}


def audit(
    db: Session,
    *,
    user_id: str,
    project_id: Optional[str],
    action: str,
    correlation_id: str,
    metadata: Optional[dict] = None,
) -> None:
    safe_metadata = {}
    for key, value in (metadata or {}).items():
        safe_metadata[key] = "[REDACTED]" if key in SENSITIVE_METADATA_KEYS else value
    db.add(
        AuditLog(
            user_id=user_id,
            project_id=project_id,
            action=action,
            correlation_id=correlation_id,
            metadata_json=safe_metadata,
        )
    )
