import json
import sys
import types
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPOSITORY_ROOT / "apps" / "api" / "src"
if str(API_SRC) in sys.path:
    sys.path.remove(str(API_SRC))
sys.path.insert(0, str(REPOSITORY_ROOT))
core_package = types.ModuleType("core")
core_package.__path__ = [str(REPOSITORY_ROOT / "core")]
sys.modules["core"] = core_package

from core.evidence_schema import (  # noqa: E402
    ConfidenceBreakdown,
    ConfidenceFactor,
    ConfidenceLevel,
    EvidenceRecord,
    EvidenceSourceType,
    RelatedEvidenceEntities,
    confidence_level_for_score,
    evidence_index_to_dict,
    load_evidence_index,
    save_evidence_index,
)


def _confidence(score: float = 0.8) -> ConfidenceBreakdown:
    return ConfidenceBreakdown(
        score=score,
        level=confidence_level_for_score(score),
        calculation={
            "source_reliability": ConfidenceFactor(
                weight=0.3,
                value=1.0,
                weighted_score=0.3,
            ),
            "entity_correlation": ConfidenceFactor(
                weight=0.25,
                value=1.0,
                weighted_score=0.25,
            ),
        },
        explanation="The source is reliable and links to graph context.",
    )


def _record() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="evidence:test-001",
        title="Test evidence",
        summary="A small evidence record for schema validation.",
        source_type=EvidenceSourceType.ATTACK_CHAIN_REPORT,
        source_path="reports/attack-chain-analysis.json",
        source_reference="attack-chain:sim-full-lifecycle-001",
        timestamp="2026-06-01T18:43:55Z",
        related_entities=RelatedEvidenceEntities(
            events=["event:64ef7517-c6bf-419f-99d1-2c6d93984694"],
            mitre_techniques=["mitre:T1078"],
            attack_chains=["attack-chain:sim-full-lifecycle-001"],
        ),
        confidence=_confidence(),
    )


def test_confidence_level_for_score_maps_ranges() -> None:
    assert confidence_level_for_score(0.0) == ConfidenceLevel.LOW
    assert confidence_level_for_score(0.39) == ConfidenceLevel.LOW
    assert confidence_level_for_score(0.4) == ConfidenceLevel.MEDIUM
    assert confidence_level_for_score(0.69) == ConfidenceLevel.MEDIUM
    assert confidence_level_for_score(0.7) == ConfidenceLevel.HIGH
    assert confidence_level_for_score(1.0) == ConfidenceLevel.HIGH


def test_evidence_record_round_trips_to_dict() -> None:
    record = _record()

    restored = EvidenceRecord.from_dict(record.to_dict())

    assert restored == record
    assert restored.related_entities.all_entity_ids()
    assert restored.to_dict()["source_type"] == "attack_chain_report"


def test_evidence_requires_prefixed_id() -> None:
    with pytest.raises(ValueError, match="Evidence IDs"):
        EvidenceRecord(
            evidence_id="test-001",
            title="Bad evidence",
            summary="Missing prefix.",
            source_type=EvidenceSourceType.SOC_EVENT,
            source_path="reports/soc-events.jsonl",
            source_reference="event:1",
            timestamp="2026-06-01T18:43:55Z",
            related_entities=RelatedEvidenceEntities(events=["event:1"]),
            confidence=_confidence(),
        )


def test_evidence_requires_at_least_one_related_entity() -> None:
    with pytest.raises(ValueError, match="at least one graph entity"):
        RelatedEvidenceEntities()


def test_confidence_level_must_match_score() -> None:
    with pytest.raises(ValueError, match="does not match"):
        ConfidenceBreakdown(
            score=0.8,
            level=ConfidenceLevel.LOW,
            calculation={},
            explanation="Mismatch should fail.",
        )


def test_evidence_index_serializes_deterministically() -> None:
    record = _record()

    payload = evidence_index_to_dict([record])

    assert payload["schema_version"] == "1.0"
    assert payload["evidence"][0]["evidence_id"] == "evidence:test-001"


def test_save_and_load_evidence_index(tmp_path: Path) -> None:
    output_path = tmp_path / "evidence-index.json"
    record = _record()

    save_evidence_index(output_path, [record])
    restored = load_evidence_index(output_path)

    assert restored == [record]
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema_version"] == "1.0"


def test_sample_evidence_index_loads() -> None:
    records = load_evidence_index(REPOSITORY_ROOT / "reports" / "evidence-index.json")

    assert len(records) == 3
    assert all(record.evidence_id.startswith("evidence:") for record in records)
    assert all(record.related_entities.all_entity_ids() for record in records)
    assert all(record.confidence.explanation for record in records)
