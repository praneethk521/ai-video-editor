from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings, validate_auth_configuration
from app.main import create_app


def test_allowed_cors_preflight_returns_explicit_origin(monkeypatch):
    monkeypatch.setattr(settings, "cors_allowed_origins", "https://dashboard.example.test")
    with TestClient(create_app()) as client:
        response = client.options(
            "/auth/me",
            headers={
                "Origin": "https://dashboard.example.test",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://dashboard.example.test"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_disallowed_cors_preflight_is_rejected(client):
    response = client.options(
        "/auth/me",
        headers={
            "Origin": "https://untrusted.example.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_untrusted_host_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "trusted_hosts", "api.example.test,testserver")
    with TestClient(create_app(), base_url="http://attacker.example.test") as client:
        response = client.get("/healthz")

    assert response.status_code == 400


def test_api_responses_include_private_security_headers(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"cors_allowed_origins": "http://dashboard.example.test"}, "explicit HTTPS origins"),
        ({"cors_allowed_origins": ""}, "explicit HTTPS origins"),
        ({"trusted_hosts": "*"}, "explicit hosts"),
        ({"trusted_hosts": ""}, "explicit hosts"),
    ],
)
def test_production_http_boundaries_fail_closed(overrides, message):
    configuration = {
        "app_env": "production",
        "user_auth_mode": "oidc",
        "legacy_service_token_enabled": False,
        "oidc_issuer_url": "https://identity.example.test",
        "oidc_audience": "ai-video-editor",
        "oidc_jwks_url": "https://identity.example.test/jwks.json",
        "cors_allowed_origins": "https://dashboard.example.test",
        "trusted_hosts": "api.example.test",
        **overrides,
    }
    value = Settings(_env_file=None, **configuration)

    with pytest.raises(RuntimeError, match=message):
        validate_auth_configuration(value)
