"""Batch B (R2): Host header validation via TrustedHostMiddleware."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

API = "/api/v1"


def test_allowed_host_header_returns_normal_response():
    with TestClient(app, base_url="http://testserver") as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json()["service"] == settings.app_name


def test_localhost_host_header_is_allowed():
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/")
    assert response.status_code == 200


def test_unauthorized_host_header_returns_400():
    with TestClient(app, base_url="http://evil.example") as client:
        response = client.get("/")
    assert response.status_code == 400


def test_unauthorized_host_header_rejected_for_api_route():
    with TestClient(app, base_url="http://evil.example") as client:
        response = client.get(f"{API}/health")
    assert response.status_code == 400


def test_health_and_readiness_work_with_allowed_hosts():
    with TestClient(app, base_url="http://testserver") as client:
        liveness = client.get("/health")
        readiness = client.get(f"{API}/health")
    assert liveness.status_code == 200
    assert liveness.json()["status"] == "ok"
    assert readiness.status_code in (200, 503)
    assert "database" in readiness.json()


def test_production_rejects_missing_allowed_hosts():
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS must be an explicit non-empty"):
        settings.__class__(
            environment="production",
            debug=False,
            database_url="postgresql+psycopg://loopmesh:loopmesh@localhost:5432/loopmesh",
            cors_origins="https://app.example.com",
            allowed_hosts="",
            trusted_proxy_ips="10.0.0.1",
        ).validate_runtime_security()


def test_production_rejects_wildcard_allowed_hosts():
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS must be an explicit non-empty"):
        settings.__class__(
            environment="production",
            debug=False,
            database_url="postgresql+psycopg://loopmesh:loopmesh@localhost:5432/loopmesh",
            cors_origins="https://app.example.com",
            allowed_hosts="*",
            trusted_proxy_ips="10.0.0.1",
        ).validate_runtime_security()


def test_production_rejects_allowlist_containing_wildcard():
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS must be an explicit non-empty"):
        settings.__class__(
            environment="production",
            debug=False,
            database_url="postgresql+psycopg://loopmesh:loopmesh@localhost:5432/loopmesh",
            cors_origins="https://app.example.com",
            allowed_hosts="api.example.com,*",
            trusted_proxy_ips="10.0.0.1",
        ).validate_runtime_security()


def test_production_accepts_explicit_allowed_hosts():
    cfg = settings.__class__(
        environment="production",
        debug=False,
        database_url="postgresql+psycopg://loopmesh:loopmesh@localhost:5432/loopmesh",
        cors_origins="https://app.example.com",
        allowed_hosts="api.example.com,internal.example.com",
        trusted_proxy_ips="10.0.0.1",
    )
    cfg.validate_runtime_security()
