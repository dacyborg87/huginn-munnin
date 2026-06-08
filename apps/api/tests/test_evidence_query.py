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

from core.evidence_query import (  # noqa: E402
    EvidenceQuery,
    EvidenceQueryResult,
    generate_sample_evidence_query_output,
)


def test_evidence_query_loads_records_from_json() -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)

    assert len(query.records) == 6
    assert {
        "evidence:post-auth-visibility-gap-001",
        "evidence:weakness-15953a2c-3b98-4640-9401-1306f95162e3",
    }.issubset({record.evidence_id for record in query.records})


def test_find_evidence_by_finding_id() -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)
    result = query.find_by_finding_id(
        "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
    )

    assert isinstance(result, EvidenceQueryResult)
    assert result.matches
    assert all(result.explanation for _ in result.matches)
    assert any(
        record.source_reference == "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
        for record in result.matches
    )


def test_find_evidence_by_mitre_technique() -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)
    result = query.find_by_mitre_technique("T1078")

    assert result.query_type == "mitre_technique"
    assert result.matches
    assert all(
        "mitre:T1078" in record.related_entities.mitre_techniques
        for record in result.matches
    )


def test_find_evidence_by_related_weakness() -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)
    result = query.find_by_related_weakness(
        "15953a2c-3b98-4640-9401-1306f95162e3"
    )

    assert result.matches
    assert all(
        "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
        in record.related_entities.architecture_weaknesses
        or record.source_reference == "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
        for record in result.matches
    )


def test_find_evidence_by_recommendation() -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)
    result = query.find_by_recommendation("design.post_auth_telemetry_layer")

    assert result.matches
    assert all(
        "recommendation:design.post_auth_telemetry_layer"
        in record.related_entities.defense_recommendations
        or record.source_reference == "recommendation:design.post_auth_telemetry_layer"
        for record in result.matches
    )


def test_find_evidence_by_confidence_level() -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)
    result = query.find_by_confidence_level("high")

    assert result.matches
    assert all(record.confidence.level.value == "high" for record in result.matches)


def test_empty_result_has_plain_english_explanation() -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)
    result = query.find_by_finding_id("finding:does-not-exist")

    assert result.matches == []
    assert result.to_dict()["match_count"] == 0
    assert "No evidence records matched" in result.explanation
    assert "evidence gap" in result.explanation


def test_sample_query_output_can_be_saved(tmp_path: Path) -> None:
    query = EvidenceQuery(REPOSITORY_ROOT)
    output = query.save_sample_query_output(tmp_path / "evidence-query-output.json")
    payload = json.loads((tmp_path / "evidence-query-output.json").read_text(encoding="utf-8"))

    assert output["evidence_record_count"] == 6
    assert payload["evidence_record_count"] == 6
    assert len(payload["queries"]) == 5
    assert any(item["match_count"] == 0 for item in payload["queries"])


def test_committed_sample_evidence_query_output_loads() -> None:
    output = generate_sample_evidence_query_output(REPOSITORY_ROOT)
    report_path = REPOSITORY_ROOT / "reports" / "evidence-query-output.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert output["evidence_record_count"] == payload["evidence_record_count"]
    assert payload["queries"]
