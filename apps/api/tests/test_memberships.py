from __future__ import annotations

from app.core.security import CurrentUser, get_current_user
from app.models.entities import AuditLog, Project, ProjectMember, TeamMember, User


def test_owner_manages_direct_and_team_project_memberships(client, auth_headers, db_session):
    project_response = client.post("/projects", json={"name": "Shared launch"}, headers=auth_headers)
    team_response = client.post("/teams", json={"name": "Editors"}, headers=auth_headers)
    assert project_response.status_code == 201
    assert team_response.status_code == 201
    project_id = project_response.json()["id"]
    team_id = team_response.json()["id"]
    target = User(id="target-user", email="target@example.test", role="user")
    db_session.add(target)
    db_session.commit()

    direct = client.put(
        f"/projects/{project_id}/members/users",
        json={"email": "TARGET@example.test", "role": "reviewer"},
        headers=auth_headers,
    )
    team_member = client.put(
        f"/teams/{team_id}/members",
        json={"email": target.email, "role": "operator"},
        headers=auth_headers,
    )
    team_project = client.put(
        f"/projects/{project_id}/members/teams/{team_id}",
        json={"role": "operator"},
        headers=auth_headers,
    )
    listed = client.get(f"/projects/{project_id}/members", headers=auth_headers)

    assert direct.status_code == 200
    assert direct.json()["role"] == "reviewer"
    assert team_member.status_code == 200
    assert team_project.status_code == 200
    assert {(row["principal_type"], row["principal_id"]) for row in listed.json()["members"]} == {
        ("user", target.id),
        ("team", team_id),
    }
    actions = {row.action for row in db_session.query(AuditLog).all()}
    assert "project.membership.user.updated" in actions
    assert "project.membership.team.updated" in actions
    assert "team.membership.updated" in actions


def test_team_membership_grants_project_role_capped_by_team_role(client, auth_headers, db_session):
    project_response = client.post("/projects", json={"name": "Team access"}, headers=auth_headers)
    team_response = client.post("/teams", json={"name": "Review crew"}, headers=auth_headers)
    project_id = project_response.json()["id"]
    team_id = team_response.json()["id"]
    target = User(id="team-reviewer", email="team-reviewer@example.test", role="user")
    db_session.add(target)
    db_session.commit()
    client.put(f"/teams/{team_id}/members/{target.id}", json={"role": "reviewer"}, headers=auth_headers)
    client.put(
        f"/projects/{project_id}/members/teams/{team_id}", json={"role": "operator"}, headers=auth_headers
    )

    def team_reviewer():
        return CurrentUser(target.id, target.email)

    client.app.dependency_overrides[get_current_user] = team_reviewer
    try:
        readable = client.get(f"/projects/{project_id}/status", headers=auth_headers)
        blocked = client.post(
            f"/projects/{project_id}/connect-drive",
            json={"folder_url": "https://drive.google.com/drive/folders/private-folder"},
            headers=auth_headers,
        )
    finally:
        client.app.dependency_overrides.clear()

    assert readable.status_code == 200
    assert blocked.status_code == 403


def test_non_owner_cannot_administer_project_memberships(client, auth_headers, db_session):
    project = Project(name="Owner controlled", owner_user_id="owner-user")
    reviewer = User(id="reviewer-user", email="reviewer@example.test", role="user")
    target = User(id="target-user", email="target@example.test", role="user")
    db_session.add_all([project, reviewer, target])
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=reviewer.id, role="reviewer"))
    db_session.commit()

    def reviewer_user():
        return CurrentUser(reviewer.id, reviewer.email)

    client.app.dependency_overrides[get_current_user] = reviewer_user
    try:
        response = client.put(
            f"/projects/{project.id}/members/users/{target.id}",
            json={"role": "viewer"},
            headers=auth_headers,
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 403
    assert (
        db_session.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == target.id)
        .one_or_none()
        is None
    )


def test_team_cannot_lose_its_last_owner(client, auth_headers, db_session):
    team_response = client.post("/teams", json={"name": "Protected owners"}, headers=auth_headers)
    team_id = team_response.json()["id"]

    blocked_delete = client.delete(f"/teams/{team_id}/members/local-user", headers=auth_headers)
    blocked_demotion = client.put(
        f"/teams/{team_id}/members/local-user", json={"role": "operator"}, headers=auth_headers
    )

    assert blocked_delete.status_code == 409
    assert blocked_demotion.status_code == 409
    owner = (
        db_session.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == "local-user")
        .one()
    )
    assert owner.role == "owner"


def test_team_owner_can_transfer_ownership(client, auth_headers, db_session):
    team_response = client.post("/teams", json={"name": "Ownership transfer"}, headers=auth_headers)
    team_id = team_response.json()["id"]
    successor = User(id="successor", email="successor@example.test", role="user")
    db_session.add(successor)
    db_session.commit()

    added = client.put(
        f"/teams/{team_id}/members/{successor.id}", json={"role": "owner"}, headers=auth_headers
    )
    removed = client.delete(f"/teams/{team_id}/members/local-user", headers=auth_headers)

    assert added.status_code == 200
    assert removed.status_code == 204
    assert (
        db_session.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == successor.id, TeamMember.role == "owner")
        .one_or_none()
        is not None
    )
