from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.security import CurrentUser, get_current_user, hash_service_token
from app.models.entities import Project, ProjectMember, RenderJob, ServiceToken, Team, TeamMember, TimelinePlan
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


def test_project_viewer_can_read_project_status(client, auth_headers, db_session):
    project = Project(name="Viewer-visible project", owner_user_id="owner-user")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id="viewer-user", role="viewer"))
    db_session.commit()

    def viewer_user():
        return CurrentUser("viewer-user", "viewer@example.test")

    client.app.dependency_overrides[get_current_user] = viewer_user
    try:
        response = client.get(f"/projects/{project.id}/status", headers=auth_headers)
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["project_id"] == project.id


def test_project_viewer_cannot_render_project(client, auth_headers, db_session):
    project = Project(name="Viewer-read-only project", owner_user_id="owner-user")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id="viewer-user", role="viewer"))
    db_session.commit()

    def viewer_user():
        return CurrentUser("viewer-user", "viewer@example.test")

    client.app.dependency_overrides[get_current_user] = viewer_user
    try:
        response = client.post(f"/projects/{project.id}/render", json={"variants": ["youtube_16x9"]}, headers=auth_headers)
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 403


def test_project_operator_can_connect_drive(client, auth_headers, db_session):
    project = Project(name="Operator project", owner_user_id="owner-user")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id="operator-user", role="operator"))
    db_session.commit()

    def operator_user():
        return CurrentUser("operator-user", "operator@example.test")

    client.app.dependency_overrides[get_current_user] = operator_user
    try:
        response = client.post(
            f"/projects/{project.id}/connect-drive",
            json={"folder_url": "https://drive.google.com/drive/folders/source-folder"},
            headers=auth_headers,
        )
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["authorization_url"] is not None


def test_project_reviewer_can_review_but_not_connect_drive(client, auth_headers, db_session):
    project = Project(name="Reviewer project", owner_user_id="owner-user")
    plan = TimelinePlan(
        project_id=project.id,
        variant="youtube_16x9",
        confidence_score=0.9,
        plan_json={"confidence_score": 0.9, "tracks": []},
    )
    db_session.add(project)
    db_session.flush()
    plan.project_id = project.id
    db_session.add_all(
        [
            plan,
            ProjectMember(project_id=project.id, user_id="reviewer-user", role="reviewer"),
        ]
    )
    db_session.commit()

    def reviewer_user():
        return CurrentUser("reviewer-user", "reviewer@example.test")

    client.app.dependency_overrides[get_current_user] = reviewer_user
    try:
        approved = client.post(
            f"/projects/{project.id}/plans/{plan.id}/approve",
            json={"notes": "Approved by reviewer."},
            headers=auth_headers,
        )
        blocked = client.post(
            f"/projects/{project.id}/connect-drive",
            json={"folder_url": "https://drive.google.com/drive/folders/source-folder"},
            headers=auth_headers,
        )
    finally:
        client.app.dependency_overrides.clear()

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert blocked.status_code == 403


def test_project_operator_can_preview_but_not_execute_retention_cleanup(client, auth_headers, db_session):
    project = Project(name="Retention operator project", owner_user_id="owner-user")
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id="operator-user", role="operator"))
    db_session.commit()

    def operator_user():
        return CurrentUser("operator-user", "operator@example.test")

    client.app.dependency_overrides[get_current_user] = operator_user
    try:
        preview = client.post(
            f"/projects/{project.id}/outputs/retention/cleanup",
            json={"dry_run": True},
            headers=auth_headers,
        )
        execution = client.post(
            f"/projects/{project.id}/outputs/retention/cleanup",
            json={"dry_run": False},
            headers=auth_headers,
        )
    finally:
        client.app.dependency_overrides.clear()

    assert preview.status_code == 200
    assert execution.status_code == 403


def test_admin_can_delete_project(client, auth_headers, db_session):
    project = Project(name="Admin project", owner_user_id="owner-user")
    db_session.add(project)
    db_session.commit()

    def admin_user():
        return CurrentUser("admin-user", "admin@example.test", role="admin")

    client.app.dependency_overrides[get_current_user] = admin_user
    try:
        response = client.delete(f"/projects/{project.id}", headers=auth_headers)
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 204


def test_project_read_denies_non_member(client, auth_headers, db_session):
    project = Project(name="Private project", owner_user_id="owner-user")
    db_session.add(project)
    db_session.commit()

    def stranger_user():
        return CurrentUser("stranger-user", "stranger@example.test")

    client.app.dependency_overrides[get_current_user] = stranger_user
    try:
        response = client.get(f"/projects/{project.id}/status", headers=auth_headers)
    finally:
        client.app.dependency_overrides.clear()

    assert response.status_code == 403


def test_project_scoped_service_token_can_update_own_render_job(client, db_session):
    project = Project(name="Scoped worker project", owner_user_id="owner-user")
    db_session.add(project)
    db_session.flush()
    plan = TimelinePlan(
        project_id=project.id,
        variant="youtube_16x9",
        confidence_score=0.9,
        plan_json={"confidence_score": 0.9, "tracks": []},
    )
    db_session.add(plan)
    db_session.flush()
    job = RenderJob(project_id=project.id, timeline_plan_id=plan.id, variant="youtube_16x9")
    token_value = "worker-token"
    db_session.add_all(
        [
            job,
            ServiceToken(
                name="Project render worker",
                token_hash=hash_service_token(token_value),
                scope="render",
                role="worker",
                project_id=project.id,
            ),
        ]
    )
    db_session.commit()

    headers = {"Authorization": f"Bearer {token_value}"}
    response = client.post(f"/internal/render-jobs/{job.id}/running", headers=headers)
    user_api_response = client.get(f"/projects/{project.id}/status", headers=headers)

    db_session.refresh(job)
    assert response.status_code == 204
    assert job.status.value == "running"
    assert user_api_response.status_code == 401


def test_project_scoped_service_token_cannot_update_other_project_job(client, db_session):
    allowed_project = Project(name="Allowed project", owner_user_id="owner-user")
    other_project = Project(name="Other project", owner_user_id="owner-user")
    db_session.add_all([allowed_project, other_project])
    db_session.flush()
    other_plan = TimelinePlan(
        project_id=other_project.id,
        variant="youtube_16x9",
        confidence_score=0.9,
        plan_json={"confidence_score": 0.9, "tracks": []},
    )
    db_session.add(other_plan)
    db_session.flush()
    other_job = RenderJob(project_id=other_project.id, timeline_plan_id=other_plan.id, variant="youtube_16x9")
    token_value = "wrong-project-worker-token"
    db_session.add_all(
        [
            other_job,
            ServiceToken(
                name="Allowed project worker",
                token_hash=hash_service_token(token_value),
                scope="render",
                role="worker",
                project_id=allowed_project.id,
            ),
        ]
    )
    db_session.commit()

    response = client.post(
        f"/internal/render-jobs/{other_job.id}/running",
        headers={"Authorization": f"Bearer {token_value}"},
    )

    db_session.refresh(other_job)
    assert response.status_code == 403
    assert other_job.status.value == "queued"
