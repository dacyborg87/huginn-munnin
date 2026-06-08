import json
import sys
import types
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPOSITORY_ROOT / "apps" / "api" / "src"
if str(API_SRC) in sys.path:
    sys.path.remove(str(API_SRC))
sys.path.insert(0, str(REPOSITORY_ROOT))
core_package = types.ModuleType("core")
core_package.__path__ = [str(REPOSITORY_ROOT / "core")]
sys.modules["core"] = core_package

from core.evidence_schema import EvidenceRecord, load_evidence_index  # noqa: E402
from core.ingest.real_data_evidence import (  # noqa: E402
    build_real_data_evidence,
    generate_sample_real_data_evidence_output,
)
from core.ingest.wazuh_parser import EventRecord  # noqa: E402


def _event(
    event_id: str,
    mitre_techniques: list[str],
    severity: str = "high",
) -> EventRecord:
    return EventRecord(
        id=event_id,
        timestamp="2026-06-08T14:22:31.000Z",
        source="wazuh",
        rule_id="60122",
        description="Multiple Windows logon failures",
        host="windows-endpoint-01",
        mitre_techniques=mitre_techniques,
        severity=severity,
    )


def test_build_real_data_evidence_creates_records_for_wazuh_events() -> None:
    records = build_real_data_evidence([
        _event("1700000000.12345", ["T1110", "T1078"]),
    ], persist=False)

    assert len(records) == 1
    record = records[0]
    assert isinstance(record, EvidenceRecord)
    assert record.evidence_id == "evidence:real-data-event-1700000000-12345"
    assert record.source_reference == "event:1700000000.12345"
    assert record.related_entities.events == ["event:1700000000.12345"]
    assert record.related_entities.mitre_techniques == ["mitre:T1078", "mitre:T1110"]
    assert "60122" in record.summary
    assert "high" in record.summary


def test_build_real_data_evidence_uses_existing_confidence_model() -> None:
    records = build_real_data_evidence([
        _event("1700000000.12345", ["T1110"], severity="critical"),
    ], persist=False)
    confidence = records[0].confidence

    assert confidence.level.value == "high"
    assert confidence.score >= 0.7
    assert confidence.calculation
    assert "Wazuh rule 60122" in confidence.explanation
    assert "included MITRE technique context" in confidence.explanation


def test_build_real_data_evidence_handles_events_without_mitre_as_gaps() -> None:
    records = build_real_data_evidence([
        _event("1700000002.111", [], severity="medium"),
    ], persist=False)
    record = records[0]

    assert record.related_entities.events == ["event:1700000002.111"]
    assert record.related_entities.mitre_techniques == []
    assert record.confidence.level.value == "low"
    assert record.confidence.score <= 0.35
    assert "Evidence gap" in record.title
    assert "evidence gap" in record.summary
    assert "did not include MITRE technique context" in record.confidence.explanation


def test_build_real_data_evidence_persists_sample_output(tmp_path: Path) -> None:
    output_path = tmp_path / "real-data-evidence-output.json"
    records = build_real_data_evidence([
        _event("1700000000.12345", ["T1110"]),
    ], output_path=output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert len(records) == 1
    assert payload["schema_version"] == "1.0"
    assert payload["evidence"][0]["source_reference"] == "event:1700000000.12345"
    assert load_evidence_index(output_path) == records


def test_committed_real_data_evidence_output_loads() -> None:
    generated = generate_sample_real_data_evidence_output(
        REPOSITORY_ROOT / "reports" / "real-data-evidence-output.json"
    )
    records = load_evidence_index(
        REPOSITORY_ROOT / "reports" / "real-data-evidence-output.json"
    )

    assert records == generated
    assert len(records) == 2
    assert any(record.related_entities.mitre_techniques for record in records)
    assert any(not record.related_entities.mitre_techniques for record in records)
