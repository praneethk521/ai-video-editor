from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.security import CurrentUser
from app.models.entities import Project, ProjectMember, Team, TeamMember
from app.services.authorization import project_role_for_user, require_project_role, role_allows


def test_role_ordering():
    assert role_allows("owner", "operator")
    assert role_allows("operator", "viewer")
    assert not role_allows("reviewer", "operator")


def test_project_membership_authorization(db_session):
    project = Project(name="RBAC", owner_user_id="owner-user")
    team = Team(name="Editors")
    db_session.add_all([project, team])
    db_session.flush()
    db_session.add_all(
        [
            ProjectMember(project_id=project.id, user_id="reviewer-user", role="reviewer"),
            TeamMember(team_id=team.id, user_id="operator-user", role="operator"),
            ProjectMember(project_id=project.id, team_id=team.id, role="operator"),
        ]
    )
    db_session.commit()

    assert project_role_for_user(db_session, project=project, user=CurrentUser("owner-user", "owner@example.test")) == "owner"
    assert (
        project_role_for_user(db_session, project=project, user=CurrentUser("admin-user", "admin@example.test", role="admin"))
        == "admin"
    )
    assert (
        project_role_for_user(db_session, project=project, user=CurrentUser("reviewer-user", "reviewer@example.test"))
        == "reviewer"
    )
    assert (
        project_role_for_user(db_session, project=project, user=CurrentUser("operator-user", "operator@example.test"))
        == "operator"
    )

    assert require_project_role(db_session, project=project, user=CurrentUser("operator-user", "operator@example.test"), minimum_role="viewer") == "operator"
    with pytest.raises(HTTPException) as exc:
        require_project_role(
            db_session,
            project=project,
            user=CurrentUser("reviewer-user", "reviewer@example.test"),
            minimum_role="operator",
        )
    assert exc.value.status_code == 403
