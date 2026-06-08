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

from core.evidence_builder import EvidenceBuilder, build_evidence_from_graph  # noqa: E402
from core.evidence_schema import (  # noqa: E402
    EvidenceRecord,
    EvidenceSourceType,
    load_evidence_index,
)


def test_evidence_builder_creates_records_from_graph_relationships() -> None:
    records = build_evidence_from_graph(REPOSITORY_ROOT, persist=False)

    assert len(records) == 3
    assert all(isinstance(record, EvidenceRecord) for record in records)
    assert {
        "weakness:15953a2c-3b98-4640-9401-1306f95162e3",
        "weakness:72f28a3e-9cd6-4559-9859-a5c091d28576",
        "weakness:9cc29804-189f-488b-bd76-abf3ebdbf8b3",
    } == {
        record.source_reference
        for record in records
    }


def test_evidence_builder_links_findings_to_graph_entities() -> None:
    records = build_evidence_from_graph(REPOSITORY_ROOT, persist=False)
    post_auth = next(
        record
        for record in records
        if record.source_reference == "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
    )

    assert post_auth.source_type == EvidenceSourceType.ARCHITECTURE_REPORT
    assert "mitre:T1078" in post_auth.related_entities.mitre_techniques
    assert "mitre:T1087" in post_auth.related_entities.mitre_techniques
    assert "attack-chain:sim-full-lifecycle-001" in post_auth.related_entities.attack_chains
    assert post_auth.related_entities.events
    assert post_auth.related_entities.memory_entries
    assert "recommendation:design.post_auth_telemetry_layer" in (
        post_auth.related_entities.defense_recommendations
    )


def test_evidence_builder_confidence_has_calculation_and_explanation() -> None:
    records = build_evidence_from_graph(REPOSITORY_ROOT, persist=False)

    for record in records:
        assert 0 <= record.confidence.score <= 1
        assert record.confidence.level.value in {"low", "medium", "high"}
        assert record.confidence.calculation
        assert record.confidence.explanation
        assert "MITRE technique" in record.confidence.explanation


def test_evidence_builder_persists_output(tmp_path: Path) -> None:
    builder = EvidenceBuilder(REPOSITORY_ROOT)
    output_path = tmp_path / "evidence-builder-output.json"
    records = builder.build(persist=False)

    from core.evidence_schema import save_evidence_index

    save_evidence_index(output_path, records)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert len(payload["evidence"]) == 3
    assert load_evidence_index(output_path) == records


def test_committed_evidence_builder_output_loads() -> None:
    records = load_evidence_index(REPOSITORY_ROOT / "reports" / "evidence-builder-output.json")

    assert len(records) == 3
    assert all(record.source_path == "reports/graph-intelligence-report.json" for record in records)
    assert all(record.related_entities.architecture_weaknesses for record in records)
