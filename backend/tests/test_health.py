"""Liveness and readiness tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_does_not_require_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "LOOPMESH API"
    assert "X-Request-ID" in response.headers


def test_readiness_reports_database(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "reachable"
    assert body["environment"] == "development"


def test_openapi_document_is_served(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/materials" in paths
    assert "/api/v1/opportunities/discovery" in paths
