import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPOSITORY_ROOT / "apps" / "api" / "src"
if str(API_SRC) in sys.path:
    sys.path.remove(str(API_SRC))
sys.path.insert(0, str(API_SRC))
core_package = types.ModuleType("core")
core_package.__path__ = [str(REPOSITORY_ROOT / "core")]
sys.modules["core"] = core_package

from core.ingest.aws_guardduty_parser import AwsGuardDutyParser  # noqa: E402
from core.ingest.wazuh_parser import EventRecord  # noqa: E402
from huginn_muninn_api.core.guardduty_ingest_api import GuardDutyIngestApi  # noqa: E402


GUARDDUTY_FINDING = {
    "id": "test-gd-ingest-001",
    "type": "Trojan:EC2/BlackholeTraffic",
    "title": "EC2 instance communicating with known black hole IP",
    "severity": 8.0,
    "createdAt": "2026-06-17T00:00:00Z",
    "updatedAt": "2026-06-17T00:01:00Z",
    "resource": {
        "resourceType": "Instance",
        "instanceDetails": {
            "instanceId": "i-0synthetic123",
        },
    },
}


@dataclass
class RelatedEntities:
    mitre_techniques: list[str]


@dataclass
class FakeEvidenceRecord:
    evidence_id: str
    mitre_techniques: list[str]

    @property
    def related_entities(self) -> RelatedEntities:
        return RelatedEntities(self.mitre_techniques)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "related_entities": {"mitre_techniques": self.mitre_techniques},
        }


class FakeGraph:
    pass


def _finding(finding_id: str = "test-gd-ingest-001") -> dict[str, Any]:
    return {**GUARDDUTY_FINDING, "id": finding_id}


def _api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GuardDutyIngestApi:
    def graph_ingestor(events: list[EventRecord], graph: FakeGraph) -> tuple[FakeGraph, dict[str, int]]:
        technique_count = len({technique for event in events for technique in event.mitre_techniques})
        relationship_count = sum(len(event.mitre_techniques) for event in events)
        return graph, {
            "events_added": len(events),
            "techniques_added": technique_count,
            "relationships_added": relationship_count,
            "duplicates_skipped": 0,
        }

    def evidence_builder(
        events: list[EventRecord],
        graph: FakeGraph,
        *,
        persist: bool,
    ) -> list[FakeEvidenceRecord]:
        return [
            FakeEvidenceRecord(
                evidence_id=f"evidence:{event.id or index}",
                mitre_techniques=[
                    technique if technique.startswith("mitre:") else f"mitre:{technique}"
                    for technique in event.mitre_techniques
                ],
            )
            for index, event in enumerate(events)
        ]

    api = GuardDutyIngestApi(tmp_path)
    monkeypatch.setattr(
        api,
        "_repository_modules",
        lambda: {
            "AwsGuardDutyParser": AwsGuardDutyParser,
            "KnowledgeGraph": FakeGraph,
            "ingest_event_records": graph_ingestor,
            "build_real_data_evidence": evidence_builder,
        },
    )
    return api


def test_single_valid_finding_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _api(tmp_path, monkeypatch).ingest(_finding())

    assert response["status"] == "accepted"
    assert response["records_received"] == 1
    assert response["records_parsed"] == 1


def test_list_of_valid_findings_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest([_finding("finding-1"), _finding("finding-2")])

    assert response["records_received"] == 2
    assert response["records_parsed"] == 2
    assert response["events_added"] == 2


def test_response_includes_aws_guardduty_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest(_finding())

    assert response["source"] == "aws_guardduty"


def test_response_includes_all_required_summary_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest(_finding())

    assert {
        "records_received",
        "records_parsed",
        "records_skipped",
        "events_added",
        "techniques_added",
        "evidence_records_created",
        "evidence_gaps_created",
    }.issubset(response)


def test_malformed_non_dict_item_in_list_is_skipped_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest([_finding(), "not-a-finding"])

    assert response["records_received"] == 2
    assert response["records_parsed"] == 1
    assert response["records_skipped"] == 1


def test_finding_missing_required_fields_is_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest([_finding(), {"id": "missing-type"}])

    assert response["records_received"] == 2
    assert response["records_parsed"] == 1
    assert response["records_skipped"] == 1


def test_empty_list_input_returns_accepted_with_zero_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest([])

    assert response["status"] == "accepted"
    assert response["records_received"] == 0
    assert response["records_parsed"] == 0
    assert response["records_skipped"] == 0
    assert response["events_added"] == 0
    assert response["techniques_added"] == 0
    assert response["evidence_records_created"] == 0
    assert response["evidence_gaps_created"] == 0


def test_non_dict_non_list_payload_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="GuardDuty ingestion payload"):
        GuardDutyIngestApi(tmp_path).ingest("not-a-payload")  # type: ignore[arg-type]


def test_response_message_matches_dashboard_refresh_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest(_finding())

    assert response["message"] == "Ingestion complete. Dashboard will refresh within 30 seconds."


def test_main_declares_guardduty_ingest_route_without_testclient() -> None:
    main_source = (API_SRC / "huginn_muninn_api" / "main.py").read_text(encoding="utf-8")

    assert "GuardDutyIngestApi" in main_source
    assert '@app.post("/ingest/guardduty")' in main_source
    assert "guardduty_ingest_api.ingest(payload)" in main_source


def test_report_uses_existing_live_telemetry_format(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _api(tmp_path, monkeypatch).ingest(_finding())
    report_path = tmp_path / "reports" / "real-data-pipeline-output.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert response["records_parsed"] == 1
    assert report["schema_version"] == "1.0"
    assert report["source_path"] == "POST /ingest/guardduty"
    assert report["summary"]["records_read"] == 1
    assert report["summary"]["records_parsed"] == 1
    assert report["evidence_records"]
