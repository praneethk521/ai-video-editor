from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import ServiceToken, User

bearer = HTTPBearer(auto_error=False)
INTERNAL_SUPER_SCOPES = {"admin", "internal", "orchestrator"}
WORKER_SCOPES = {"worker"}


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str = "user"
    service_scope: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class CurrentServiceToken:
    id: str
    role: str
    scope: str
    project_id: str | None = None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    token = credentials.credentials
    service_user, stored_service_token = get_orchestrator_user(db, token)
    if service_user is not None:
        user = service_user
    elif stored_service_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="service token not allowed")
    elif settings.user_auth_mode == "local_bearer":
        if token != settings.api_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
        user = CurrentUser(id="local-user", email="local@example.invalid")
    else:
        claims = decode_oidc_token(token)
        user = current_user_from_oidc_claims(claims)

    if user.service_scope is None:
        persist_user(db, user)
    request.state.user_id = user.id
    return user


def get_current_human_user(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.service_scope is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="human identity required")
    return user


def get_orchestrator_user(db: Session, token: str) -> tuple[CurrentUser | None, bool]:
    row = db.query(ServiceToken).filter(ServiceToken.token_hash == hash_service_token(token)).one_or_none()
    if row is None:
        return None, False
    if row.status != "active" or service_token_expired(row.expires_at):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="inactive service token")
    scopes = {scope.strip() for scope in row.scope.split(",") if scope.strip()}
    if "orchestrator" not in scopes:
        return None, True
    return (
        CurrentUser(
            id=row.id,
            email=f"{row.id}@service.invalid",
            service_scope="orchestrator",
            project_id=row.project_id,
        ),
        True,
    )


@lru_cache(maxsize=4)
def get_oidc_jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True)


def decode_oidc_token(token: str) -> dict:
    algorithms = [algorithm.strip() for algorithm in settings.oidc_algorithms.split(",") if algorithm.strip()]
    if not algorithms:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC algorithms not configured")
    try:
        signing_key = get_oidc_jwk_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=algorithms,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer_url,
            leeway=settings.oidc_leeway_seconds,
            options={"require": ["exp", "iat", settings.oidc_subject_claim]},
        )
    except (PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid identity token") from exc


def current_user_from_oidc_claims(claims: dict) -> CurrentUser:
    subject = claims.get(settings.oidc_subject_claim)
    email = claims.get(settings.oidc_email_claim)
    if not isinstance(subject, str) or not subject.strip() or not isinstance(email, str) or not email.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="identity token missing required claims")
    identity_digest = hashlib.sha256(f"{settings.oidc_issuer_url}\0{subject}".encode()).hexdigest()
    claimed_role = claims.get(settings.oidc_role_claim)
    role = "admin" if claimed_role == settings.oidc_admin_role else "user"
    return CurrentUser(id=f"oidc-{identity_digest[:58]}", email=email.strip().lower(), role=role)


def persist_user(db: Session, user: CurrentUser) -> None:
    email_owner = db.query(User).filter(User.email == user.email, User.id != user.id).one_or_none()
    if email_owner is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="identity email is already mapped")
    row = db.get(User, user.id)
    if row is None:
        db.add(User(id=user.id, email=user.email, role=user.role))
    else:
        row.email = user.email
        row.role = user.role
    db.commit()


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

    if settings.legacy_service_token_enabled and token == settings.api_token:
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
