from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import ServiceToken

bearer = HTTPBearer(auto_error=False)
INTERNAL_SUPER_SCOPES = {"admin", "internal", "orchestrator"}
WORKER_SCOPES = {"worker"}


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str = "owner"


@dataclass(frozen=True)
class CurrentServiceToken:
    id: str
    role: str
    scope: str
    project_id: str | None = None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    if credentials.credentials != settings.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
    user = CurrentUser(id="local-user", email="local@example.invalid")
    request.state.user_id = user.id
    return user


def hash_service_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_current_service_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentServiceToken:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    token = credentials.credentials
    row = db.query(ServiceToken).filter(ServiceToken.token_hash == hash_service_token(token)).one_or_none()
    if row is not None:
        if row.status != "active" or service_token_expired(row.expires_at):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="inactive service token")
        return CurrentServiceToken(id=row.id, role=row.role, scope=row.scope, project_id=row.project_id)

    if token == settings.api_token:
        return CurrentServiceToken(id="legacy-api-token", role="admin", scope="orchestrator")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")


def require_service_scope(token: CurrentServiceToken, *, required_scope: str, project_id: str | None = None) -> None:
    scopes = {scope.strip() for scope in token.scope.split(",") if scope.strip()}
    if token.project_id is not None and project_id is not None and token.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="service token project scope denied")
    if scopes & INTERNAL_SUPER_SCOPES:
        return
    if required_scope in scopes:
        return
    if scopes & WORKER_SCOPES and required_scope in {"render", "scan", "delivery"}:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="service token scope denied")


def service_token_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)
