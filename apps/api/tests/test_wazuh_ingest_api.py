import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPOSITORY_ROOT / "apps" / "api" / "src"
if str(API_SRC) in sys.path:
    sys.path.remove(str(API_SRC))
sys.path.insert(0, str(API_SRC))
core_package = types.ModuleType("core")
core_package.__path__ = [str(REPOSITORY_ROOT / "core")]
sys.modules["core"] = core_package

from core.ingest.wazuh_parser import EventRecord, parse_wazuh_alert  # noqa: E402
from huginn_muninn_api.core.wazuh_ingest_api import WazuhIngestApi  # noqa: E402


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


def _valid_alert(
    *,
    alert_id: str = "1700000000.12345",
    rule_id: str = "60122",
    mitre_ids: list[str] | None = None,
) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "id": rule_id,
        "level": 10,
        "description": "Multiple Windows logon failures",
    }
    if mitre_ids is not None:
        rule["mitre"] = {"id": mitre_ids}
    return {
        "id": alert_id,
        "timestamp": "2026-06-17T12:00:00.000Z",
        "agent": {"name": "windows-endpoint-01"},
        "rule": rule,
    }


def _api(tmp_path: Path) -> WazuhIngestApi:
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

    return WazuhIngestApi(
        tmp_path,
        parser=parse_wazuh_alert,
        graph_ingestor=graph_ingestor,
        evidence_builder=evidence_builder,
        graph_factory=FakeGraph,
    )


def test_single_valid_wazuh_alert_is_accepted(tmp_path: Path) -> None:
    response = _api(tmp_path).ingest(_valid_alert(mitre_ids=["T1110", "T1078"]))

    assert response["status"] == "accepted"
    assert response["records_received"] == 1
    assert response["records_parsed"] == 1
    assert response["records_skipped"] == 0
    assert response["events_added"] == 1
    assert response["techniques_added"] == 2
    assert response["relationships_added"] == 2
    assert response["evidence_records_created"] == 1
    assert response["evidence_gaps_created"] == 0


def test_list_of_wazuh_alerts_is_accepted(tmp_path: Path) -> None:
    response = _api(tmp_path).ingest(
        [
            _valid_alert(alert_id="1", rule_id="60122", mitre_ids=["T1110"]),
            _valid_alert(alert_id="2", rule_id="5710", mitre_ids=["T1110"]),
        ]
    )

    assert response["records_received"] == 2
    assert response["records_parsed"] == 2
    assert response["events_added"] == 2
    assert response["techniques_added"] == 1
    assert response["relationships_added"] == 2


def test_malformed_alert_is_skipped_safely(tmp_path: Path) -> None:
    response = _api(tmp_path).ingest([_valid_alert(mitre_ids=["T1110"]), "not-an-alert"])

    assert response["records_received"] == 2
    assert response["records_parsed"] == 1
    assert response["records_skipped"] == 1
    assert response["events_added"] == 1


def test_alert_missing_critical_fields_is_skipped(tmp_path: Path) -> None:
    response = _api(tmp_path).ingest(
        [
            _valid_alert(mitre_ids=["T1110"]),
            {"id": "missing-critical-fields", "rule": {"id": "60122"}},
        ]
    )

    assert response["records_received"] == 2
    assert response["records_parsed"] == 1
    assert response["records_skipped"] == 1
    assert response["events_added"] == 1


def test_empty_list_is_handled_safely(tmp_path: Path) -> None:
    response = _api(tmp_path).ingest([])

    assert response["records_received"] == 0
    assert response["records_parsed"] == 0
    assert response["records_skipped"] == 0
    assert response["events_added"] == 0
    assert response["evidence_records_created"] == 0
    assert response["evidence_gaps_created"] == 0


def test_evidence_gap_created_when_mitre_is_missing(tmp_path: Path) -> None:
    response = _api(tmp_path).ingest(_valid_alert(mitre_ids=None))

    assert response["records_received"] == 1
    assert response["records_parsed"] == 1
    assert response["evidence_records_created"] == 1
    assert response["evidence_gaps_created"] == 1


def test_pipeline_report_uses_existing_live_telemetry_format(tmp_path: Path) -> None:
    response = _api(tmp_path).ingest(_valid_alert(mitre_ids=["T1110"]))
    report_path = tmp_path / "reports" / "real-data-pipeline-output.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert response["records_parsed"] == 1
    assert report["schema_version"] == "1.0"
    assert report["source_path"] == "POST /ingest/wazuh"
    assert report["summary"]["records_read"] == 1
    assert report["summary"]["records_parsed"] == 1
    assert report["evidence_records"]


def test_main_declares_wazuh_ingest_route_without_testclient() -> None:
    main_source = (API_SRC / "huginn_muninn_api" / "main.py").read_text(encoding="utf-8")

    assert "WazuhIngestApi" in main_source
    assert '@app.post("/ingest/wazuh")' in main_source
    assert "wazuh_ingest_api.ingest(payload)" in main_source
