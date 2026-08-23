from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import CurrentUser, get_current_human_user
from app.db.session import get_db
from app.models.entities import Team, TeamMember, User
from app.schemas.api import (
    MembershipRoleUpdate,
    TeamCreate,
    TeamMemberRead,
    TeamMembersResponse,
    TeamRead,
    TeamsResponse,
    UserMembershipRoleUpdate,
)
from app.services.audit import audit
from app.services.authorization import role_allows, team_role_for_user

router = APIRouter(prefix="/teams", tags=["teams"])


def get_team_for_owner_or_404(
    db: Session,
    *,
    team_id: str,
    user: CurrentUser,
    request: Request,
    requested_action: str,
) -> Team:
    team = db.get(Team, team_id)
    actual_role = team_role_for_user(db, team=team, user=user) if team is not None else None
    allowed = team is not None and role_allows(actual_role, "owner")
    audit(
        db,
        user_id=user.id,
        project_id=None,
        action="authorization.team",
        correlation_id=request.state.correlation_id,
        metadata={
            "team_id": team_id,
            "requested_action": requested_action,
            "minimum_role": "owner",
            "actual_role": actual_role,
            "outcome": "allowed" if allowed else "denied",
            "reason": None if allowed else ("team_not_found" if team is None else "insufficient_team_role"),
        },
    )
    db.commit()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient team role")
    return team


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_human_user),
):
    team = Team(name=payload.name)
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    audit(
        db,
        user_id=user.id,
        project_id=None,
        action="team.created",
        correlation_id=request.state.correlation_id,
        metadata={"team_id": team.id},
    )
    db.commit()
    return TeamRead(id=team.id, name=team.name, role="owner")


@router.get("", response_model=TeamsResponse)
def list_teams(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_human_user),
):
    if user.role == "admin":
        teams = db.query(Team).order_by(Team.name).all()
        return TeamsResponse(teams=[TeamRead(id=team.id, name=team.name, role="admin") for team in teams])
    rows = (
        db.query(Team, TeamMember.role)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .filter(TeamMember.user_id == user.id)
        .order_by(Team.name)
        .all()
    )
    return TeamsResponse(teams=[TeamRead(id=team.id, name=team.name, role=role) for team, role in rows])


@router.get("/{team_id}/members", response_model=TeamMembersResponse)
def list_team_members(
    team_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_human_user),
):
    team = get_team_for_owner_or_404(
        db, team_id=team_id, user=user, request=request, requested_action="team.memberships.read"
    )
    rows = (
        db.query(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .filter(TeamMember.team_id == team.id)
        .order_by(User.email)
        .all()
    )
    return TeamMembersResponse(
        members=[TeamMemberRead(id=membership.id, user_id=row.id, email=row.email, role=membership.role) for membership, row in rows]
    )


@router.put("/{team_id}/members/{member_user_id}", response_model=TeamMemberRead)
def upsert_team_member(
    team_id: str,
    member_user_id: str,
    payload: MembershipRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_human_user),
):
    team = get_team_for_owner_or_404(
        db, team_id=team_id, user=user, request=request, requested_action="team.membership.write"
    )
    member_user = db.get(User, member_user_id)
    if member_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    membership = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == member_user.id)
        .one_or_none()
    )
    if membership is not None and membership.role == "owner" and payload.role != "owner":
        ensure_another_team_owner(db, team_id=team.id, excluded_member_id=membership.id)
    if membership is None:
        membership = TeamMember(team_id=team.id, user_id=member_user.id, role=payload.role)
        db.add(membership)
    else:
        membership.role = payload.role
    db.flush()
    audit(
        db,
        user_id=user.id,
        project_id=None,
        action="team.membership.updated",
        correlation_id=request.state.correlation_id,
        metadata={"team_id": team.id, "member_user_id": member_user.id, "role": payload.role},
    )
    db.commit()
    return TeamMemberRead(id=membership.id, user_id=member_user.id, email=member_user.email, role=membership.role)


@router.put("/{team_id}/members", response_model=TeamMemberRead)
def upsert_team_member_by_email(
    team_id: str,
    payload: UserMembershipRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_human_user),
):
    team = get_team_for_owner_or_404(
        db, team_id=team_id, user=user, request=request, requested_action="team.membership.write"
    )
    member_user = db.query(User).filter(User.email == payload.email.strip().lower()).one_or_none()
    if member_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    membership = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == member_user.id)
        .one_or_none()
    )
    if membership is not None and membership.role == "owner" and payload.role != "owner":
        ensure_another_team_owner(db, team_id=team.id, excluded_member_id=membership.id)
    if membership is None:
        membership = TeamMember(team_id=team.id, user_id=member_user.id, role=payload.role)
        db.add(membership)
    else:
        membership.role = payload.role
    db.flush()
    audit(
        db,
        user_id=user.id,
        project_id=None,
        action="team.membership.updated",
        correlation_id=request.state.correlation_id,
        metadata={"team_id": team.id, "member_user_id": member_user.id, "role": payload.role},
    )
    db.commit()
    return TeamMemberRead(id=membership.id, user_id=member_user.id, email=member_user.email, role=membership.role)


@router.delete("/{team_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team_member(
    team_id: str,
    member_user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_human_user),
):
    team = get_team_for_owner_or_404(
        db, team_id=team_id, user=user, request=request, requested_action="team.membership.delete"
    )
    membership = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team.id, TeamMember.user_id == member_user_id)
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team membership not found")
    if membership.role == "owner":
        ensure_another_team_owner(db, team_id=team.id, excluded_member_id=membership.id)
    db.delete(membership)
    audit(
        db,
        user_id=user.id,
        project_id=None,
        action="team.membership.deleted",
        correlation_id=request.state.correlation_id,
        metadata={"team_id": team.id, "member_user_id": member_user_id},
    )
    db.commit()
    return None


def ensure_another_team_owner(db: Session, *, team_id: str, excluded_member_id: str) -> None:
    another_owner = (
        db.query(TeamMember.id)
        .filter(TeamMember.team_id == team_id, TeamMember.role == "owner", TeamMember.id != excluded_member_id)
        .first()
    )
    if another_owner is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="team must retain at least one owner")
