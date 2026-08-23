from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import Settings, settings, validate_auth_configuration
from app.core.security import hash_service_token
from app.models.entities import Project, ServiceToken, User


def test_local_identity_is_persisted(client, auth_headers, db_session):
    response = client.get("/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"id": "local-user", "email": "local@example.invalid", "role": "user"}
    stored = db_session.get(User, "local-user")
    assert stored is not None
    assert stored.email == "local@example.invalid"


def test_oidc_identity_validates_and_is_persisted(client, db_session, monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    issuer = "https://identity.example.test"
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "ai-video-editor",
            "sub": "stable-provider-subject",
            "email": "Editor@Example.test",
            "role": "admin",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    monkeypatch.setattr(settings, "user_auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer_url", issuer)
    monkeypatch.setattr(settings, "oidc_audience", "ai-video-editor")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://identity.example.test/.well-known/jwks.json")
    monkeypatch.setattr(
        "app.core.security.get_oidc_jwk_client",
        lambda _: SimpleNamespace(get_signing_key_from_jwt=lambda __: SimpleNamespace(key=private_key.public_key())),
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["id"].startswith("oidc-")
    assert len(body["id"]) <= 64
    assert body["email"] == "editor@example.test"
    assert body["role"] == "admin"
    stored = db_session.get(User, body["id"])
    assert stored is not None
    assert stored.role == "admin"


def test_oidc_identity_rejects_wrong_audience(client, monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    issuer = "https://identity.example.test"
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "another-service",
            "sub": "subject",
            "email": "user@example.test",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
    )
    monkeypatch.setattr(settings, "user_auth_mode", "oidc")
    monkeypatch.setattr(settings, "oidc_issuer_url", issuer)
    monkeypatch.setattr(settings, "oidc_audience", "ai-video-editor")
    monkeypatch.setattr(settings, "oidc_jwks_url", "https://identity.example.test/.well-known/jwks.json")
    monkeypatch.setattr(
        "app.core.security.get_oidc_jwk_client",
        lambda _: SimpleNamespace(get_signing_key_from_jwt=lambda __: SimpleNamespace(key=private_key.public_key())),
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid identity token"


def test_legacy_service_token_can_be_disabled(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "legacy_service_token_enabled", False)

    response = client.get("/metrics", headers=auth_headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid service token"


def test_orchestrator_token_has_operator_access_but_not_human_administration(client, db_session, monkeypatch):
    project = Project(name="Orchestrated project", owner_user_id="owner-user")
    token_value = "stored-orchestrator-token"
    db_session.add_all(
        [
            project,
            ServiceToken(
                name="n8n",
                token_hash=hash_service_token(token_value),
                scope="orchestrator",
                role="worker",
            ),
        ]
    )
    db_session.commit()
    monkeypatch.setattr(settings, "user_auth_mode", "oidc")
    headers = {"Authorization": f"Bearer {token_value}"}

    status_response = client.get(f"/projects/{project.id}/status", headers=headers)
    analyze_response = client.post(f"/projects/{project.id}/analyze", headers=headers)
    render_response = client.post(
        f"/projects/{project.id}/render",
        json={"variants": ["youtube_16x9"]},
        headers=headers,
    )
    create_response = client.post("/projects", json={"name": "Disallowed"}, headers=headers)
    team_response = client.post("/teams", json={"name": "Disallowed"}, headers=headers)
    membership_response = client.get(f"/projects/{project.id}/members", headers=headers)

    assert status_response.status_code == 200
    assert status_response.json()["role"] == "operator"
    assert analyze_response.status_code == 422
    assert render_response.status_code == 422
    assert create_response.status_code == 403
    assert team_response.status_code == 403
    assert membership_response.status_code == 403


def test_project_scoped_orchestrator_cannot_access_another_project(client, db_session, monkeypatch):
    allowed = Project(name="Allowed", owner_user_id="owner-user")
    denied = Project(name="Denied", owner_user_id="owner-user")
    db_session.add_all([allowed, denied])
    db_session.flush()
    token_value = "project-orchestrator-token"
    db_session.add(
        ServiceToken(
            name="project n8n",
            token_hash=hash_service_token(token_value),
            scope="orchestrator",
            role="worker",
            project_id=allowed.id,
        )
    )
    db_session.commit()
    monkeypatch.setattr(settings, "user_auth_mode", "oidc")
    headers = {"Authorization": f"Bearer {token_value}"}

    allowed_response = client.get(f"/projects/{allowed.id}/status", headers=headers)
    denied_response = client.get(f"/projects/{denied.id}/status", headers=headers)

    assert allowed_response.status_code == 200
    assert denied_response.status_code == 403


@pytest.mark.parametrize(
    ("configuration", "message"),
    [
        (
            {"app_env": "production", "user_auth_mode": "local_bearer", "legacy_service_token_enabled": False},
            "production requires USER_AUTH_MODE=oidc",
        ),
        (
            {"app_env": "production", "user_auth_mode": "oidc", "legacy_service_token_enabled": True},
            "production requires LEGACY_SERVICE_TOKEN_ENABLED=false",
        ),
    ],
)
def test_production_auth_configuration_fails_closed(configuration, message):
    value = Settings(
        _env_file=None,
        oidc_issuer_url="https://identity.example.test",
        oidc_audience="ai-video-editor",
        oidc_jwks_url="https://identity.example.test/jwks.json",
        **configuration,
    )

    with pytest.raises(RuntimeError, match=message):
        validate_auth_configuration(value)


def test_oidc_configuration_requires_trust_boundaries():
    value = Settings(_env_file=None, app_env="staging", user_auth_mode="oidc")

    with pytest.raises(RuntimeError, match="OIDC_ISSUER_URL, OIDC_AUDIENCE, OIDC_JWKS_URL"):
        validate_auth_configuration(value)
