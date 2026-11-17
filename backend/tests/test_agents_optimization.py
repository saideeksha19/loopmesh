"""Agent control centre and optimization readiness tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

PLATFORM = {"X-Actor-Id": "demo-platform-admin"}


def test_agents_endpoint_reports_no_active_execution(client: TestClient) -> None:
    response = client.get("/api/v1/agents", headers=PLATFORM)
    assert response.status_code == 200
    body = response.json()

    assert body["executions_enabled"] is False
    assert body["running_agents"] == 0
    assert body["executions"] == []
    assert body["orchestration"]["implemented"] is False
    assert body["orchestration"]["framework"] == "LangGraph"
    assert len(body["agents"]) == 5
    for agent in body["agents"]:
        assert agent["status"] == "not_enabled"
        assert agent["guardrails"], "every planned agent must declare guardrails"


def test_optimization_endpoint_is_explicitly_not_implemented(client: TestClient) -> None:
    response = client.get("/api/v1/optimization", headers=PLATFORM)
    assert response.status_code == 200
    body = response.json()

    assert body["implemented"] is False
    assert body["engine"] == "Google OR-Tools CP-SAT"
    assert all(constraint["implemented"] is False for constraint in body["constraints"])
    assert "compatibility" in body["compatibility_prerequisite"].lower()


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_404"
