import sys
from pathlib import Path

from fastapi.testclient import TestClient


API_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(API_SRC))
sys.modules.pop("core", None)

from huginn_muninn_api.main import app  # noqa: E402


def test_dashboard_summary_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "live_telemetry"
    assert body["recent_events"]
    assert body["severity_breakdown"]
    assert body["top_rules"]
    assert body["top_agents"]
    assert body["evidence"]["summary"]["total_evidence_records"] == 2
    assert body["explanation"]


def test_dashboard_events_endpoint_limits_recent_events() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/events")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "security_events"
    assert body["count"] <= 20
    assert body["total_available"] >= body["count"]
    event = body["events"][0]
    assert {
        "timestamp",
        "rule_id",
        "description",
        "severity",
        "source_agent",
    }.issubset(event)


def test_dashboard_severity_breakdown_is_chart_ready() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/summary")

    assert response.status_code == 200
    breakdown = response.json()["severity_breakdown"]
    severities = {item["severity"] for item in breakdown}
    assert severities == {"critical", "high", "medium", "low", "informational"}
    assert all("count" in item and "percentage" in item for item in breakdown)
    assert sum(item["count"] for item in breakdown) > 0


def test_dashboard_rules_endpoint_aggregates_rule_ids() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/rules")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "rule_ids"
    assert body["rules"]
    assert len(body["rules"]) <= 10
    assert all(
        {"rule_id", "description", "occurrence_count"}.issubset(rule)
        for rule in body["rules"]
    )
    assert any(rule["rule_id"] == "60122" for rule in body["rules"])


def test_dashboard_agents_endpoint_aggregates_agents() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/agents")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "agents"
    assert body["agents"]
    assert len(body["agents"]) <= 10
    assert all({"agent_name", "event_count"}.issubset(agent) for agent in body["agents"])
    assert any(agent["agent_name"] == "windows-endpoint-01" for agent in body["agents"])


def test_dashboard_evidence_endpoint_reports_gaps() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/evidence")

    assert response.status_code == 200
    body = response.json()
    summary = body["summary"]
    assert summary["total_evidence_records"] == 2
    assert summary["high_confidence"] == 1
    assert summary["low_confidence"] == 1
    assert summary["evidence_gaps"] >= 1
    assert body["evidence_gaps"]
    assert any(
        "MITRE technique missing" in gap["reasons"]
        for gap in body["evidence_gaps"]
    )
