from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.models.entities import Project, ProjectMember, ProjectStatus, TeamMember

ROLE_RANKS = {
    "viewer": 10,
    "reviewer": 20,
    "operator": 30,
    "owner": 40,
    "admin": 50,
}


def role_allows(actual: str | None, required: str) -> bool:
    return ROLE_RANKS.get(actual or "", 0) >= ROLE_RANKS[required]


def stronger_role(left: str | None, right: str | None) -> str | None:
    if ROLE_RANKS.get(right or "", 0) > ROLE_RANKS.get(left or "", 0):
        return right
    return left


def weaker_role(left: str | None, right: str | None) -> str | None:
    if not left or not right:
        return None
    return left if ROLE_RANKS.get(left, 0) <= ROLE_RANKS.get(right, 0) else right


def project_role_for_user(db: Session, *, project: Project, user: CurrentUser) -> str | None:
    if user.role == "admin":
        return "admin"
    if project.owner_user_id == user.id:
        return "owner"

    direct_role = (
        db.query(ProjectMember.role)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        .scalar()
    )
    best_role = direct_role

    team_rows = (
        db.query(ProjectMember.role, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == ProjectMember.team_id)
        .filter(ProjectMember.project_id == project.id, TeamMember.user_id == user.id)
        .all()
    )
    for project_role, team_role in team_rows:
        best_role = stronger_role(best_role, weaker_role(project_role, team_role))
    return best_role


def require_project_role(db: Session, *, project: Project, user: CurrentUser, minimum_role: str) -> str:
    if project.status == ProjectStatus.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    actual_role = project_role_for_user(db, project=project, user=user)
    if not role_allows(actual_role, minimum_role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient project role")
    return actual_role or ""
