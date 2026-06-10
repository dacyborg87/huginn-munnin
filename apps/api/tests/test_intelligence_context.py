import json
import sys
from pathlib import Path


API_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(API_SRC))

from huginn_muninn_api.core.intelligence_context import IntelligenceContextBuilder  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_detects_mitre_technique_ids() -> None:
    builder = IntelligenceContextBuilder(REPOSITORY_ROOT)

    detected = builder.detect_mitre_techniques(
        "Investigate T1059, t1078, and T1562.001 activity."
    )

    assert detected == ["T1059", "T1078", "T1562.001"]


def test_context_builder_returns_json_safe_output() -> None:
    builder = IntelligenceContextBuilder(REPOSITORY_ROOT)

    context = builder.build("Check T1078 valid account activity.")

    json.dumps(context)
    assert context["summary"]["entity_searched"] == "knowledge_graph"
    assert context["detected_entities"] == ["T1078"]
    assert "T1078" in context["related_entities"]
    assert context["related_entities"]["T1078"]["connected_entities"]


def test_context_builder_handles_messages_without_mitre_ids() -> None:
    builder = IntelligenceContextBuilder(REPOSITORY_ROOT)

    context = builder.build("Summarize recent telemetry.")

    json.dumps(context)
    assert context["summary"]["entity_searched"] == "knowledge_graph"
    assert context["detected_entities"] == []
    assert context["related_entities"] == {}
