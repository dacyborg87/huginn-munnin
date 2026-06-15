import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


API_SRC = Path(__file__).resolve().parents[1] / "src"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(API_SRC))
sys.modules.pop("core", None)

from huginn_muninn_api.core.live_telemetry_api import LiveTelemetryApi  # noqa: E402


def _write_pipeline_report(
    repository_root: Path,
    evidence_records: list[dict[str, Any]],
) -> None:
    reports_dir = repository_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "real-data-pipeline-output.json").write_text(
        json.dumps({"evidence_records": evidence_records}),
        encoding="utf-8",
    )


def _evidence_record(
    *,
    evidence_id: str = "evidence-1",
    rule_id: str = "60122",
    host: str = "windows-endpoint-01",
    severity: str = "high",
    confidence_level: str = "high",
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "title": "Evidence for Wazuh alert: Windows account activity detected",
        "summary": (
            f"Wazuh rule {rule_id} on host {host} with severity {severity} "
            "created this evidence record."
        ),
        "timestamp": "2026-06-14T12:00:00Z",
        "source_reference": f"wazuh:{evidence_id}",
        "confidence": {
            "level": confidence_level,
            "score": 0.9 if confidence_level == "high" else 0.3,
            "explanation": "Confidence is based on available Wazuh alert context.",
        },
        "related_entities": {
            "events": [f"event:{evidence_id}"],
            "mitre_techniques": ["T1078"],
            "architecture_weaknesses": [],
            "defense_recommendations": ["recommendation:account-review"],
            "memory_entries": [],
        },
    }


def _fixed_clock(values: list[str]) -> Callable[[], str]:
    def clock() -> str:
        return values.pop(0)

    return clock


def test_dashboard_summary_endpoint() -> None:
    body = LiveTelemetryApi(REPOSITORY_ROOT).summary()

    assert body["entity_searched"] == "live_telemetry"
    assert body["recent_events"]
    assert body["severity_breakdown"]
    assert body["top_rules"]
    assert body["top_agents"]
    assert body["evidence"]["summary"]["total_evidence_records"] == 2
    assert body["explanation"]


def test_dashboard_events_endpoint_limits_recent_events() -> None:
    body = LiveTelemetryApi(REPOSITORY_ROOT).events()

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
    breakdown = LiveTelemetryApi(REPOSITORY_ROOT).summary()["severity_breakdown"]

    severities = {item["severity"] for item in breakdown}
    assert severities == {"critical", "high", "medium", "low", "informational"}
    assert all("count" in item and "percentage" in item for item in breakdown)
    assert sum(item["count"] for item in breakdown) > 0


def test_dashboard_rules_endpoint_aggregates_rule_ids() -> None:
    body = LiveTelemetryApi(REPOSITORY_ROOT).rules()

    assert body["entity_searched"] == "rule_ids"
    assert body["rules"]
    assert len(body["rules"]) <= 10
    assert all(
        {"rule_id", "description", "occurrence_count"}.issubset(rule)
        for rule in body["rules"]
    )
    assert any(rule["rule_id"] == "60122" for rule in body["rules"])


def test_dashboard_agents_endpoint_aggregates_agents() -> None:
    body = LiveTelemetryApi(REPOSITORY_ROOT).agents()

    assert body["entity_searched"] == "agents"
    assert body["agents"]
    assert len(body["agents"]) <= 10
    assert all({"agent_name", "event_count"}.issubset(agent) for agent in body["agents"])
    assert any(agent["agent_name"] == "windows-endpoint-01" for agent in body["agents"])


def test_dashboard_evidence_endpoint_reports_gaps() -> None:
    body = LiveTelemetryApi(REPOSITORY_ROOT).evidence()

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


def test_dashboard_last_updated_endpoint_reports_reload_state() -> None:
    body = LiveTelemetryApi(REPOSITORY_ROOT).last_updated()

    assert body["entity_searched"] == "live_telemetry_report"
    assert "last_successful_reload" in body
    assert "last_reload_error" in body
    assert body["poll_interval_seconds"] == 30.0
    assert body["source_path"].endswith("reports/real-data-pipeline-output.json")
    assert body["cache_status"] in {"empty", "ready", "ready_empty", "stale"}
    assert body["explanation"]


def test_dashboard_last_updated_route_is_wired() -> None:
    main_source = (API_SRC / "huginn_muninn_api" / "main.py").read_text(encoding="utf-8")

    assert '@app.get("/dashboard/last-updated")' in main_source
    assert "return live_telemetry_api.last_updated()" in main_source


def test_live_telemetry_serves_stale_data_when_reload_fails(
    tmp_path: Path,
    caplog: Any,
) -> None:
    api = LiveTelemetryApi(
        tmp_path,
        clock=_fixed_clock(["2026-06-14T12:00:00+00:00"]),
    )
    _write_pipeline_report(
        tmp_path,
        [_evidence_record(evidence_id="stable-record", rule_id="60122")],
    )

    assert api.reload_pipeline_report() is True
    first_updated = api.last_updated()["last_successful_reload"]
    report_path = tmp_path / "reports" / "real-data-pipeline-output.json"
    report_path.write_text("{malformed-json", encoding="utf-8")

    assert api.reload_pipeline_report() is False
    status = api.last_updated()
    assert status["last_successful_reload"] == first_updated
    assert status["last_reload_error"]
    assert status["cache_status"] == "stale"
    assert api.evidence()["summary"]["total_evidence_records"] == 1
    assert api.rules()["rules"][0]["rule_id"] == "60122"
    assert "Malformed live telemetry report" in caplog.text


def test_live_telemetry_last_updated_changes_after_successful_reload(
    tmp_path: Path,
) -> None:
    api = LiveTelemetryApi(
        tmp_path,
        clock=_fixed_clock(
            [
                "2026-06-14T12:00:00+00:00",
                "2026-06-14T12:00:30+00:00",
            ]
        ),
    )
    _write_pipeline_report(
        tmp_path,
        [_evidence_record(evidence_id="first-record", rule_id="60122")],
    )

    assert api.reload_pipeline_report() is True
    first_updated = api.last_updated()["last_successful_reload"]
    _write_pipeline_report(
        tmp_path,
        [
            _evidence_record(evidence_id="first-record", rule_id="60122"),
            _evidence_record(evidence_id="second-record", rule_id="5715"),
        ],
    )

    assert api.reload_pipeline_report() is True
    status = api.last_updated()
    assert status["last_successful_reload"] == "2026-06-14T12:00:30+00:00"
    assert status["last_successful_reload"] != first_updated
    assert status["last_reload_error"] is None
    assert status["cache_status"] == "ready"
    assert api.evidence()["summary"]["total_evidence_records"] == 2


def test_live_telemetry_missing_report_returns_useful_error_status(
    tmp_path: Path,
    caplog: Any,
) -> None:
    api = LiveTelemetryApi(tmp_path)

    assert api.reload_pipeline_report() is False
    status = api.last_updated()
    assert status["last_successful_reload"] is None
    assert status["last_reload_error"]
    assert status["source_path"].endswith("reports/real-data-pipeline-output.json")
    assert status["cache_status"] == "empty"
    assert api.evidence()["summary"]["total_evidence_records"] == 0
    assert "Unable to reload live telemetry report" in caplog.text
