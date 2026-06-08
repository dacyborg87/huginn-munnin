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

from core.ingest.graph_ingest import (  # noqa: E402
    generate_sample_graph_ingest_output,
    ingest_event_records,
    save_graph_ingest_output,
)
from core.ingest.wazuh_parser import EventRecord  # noqa: E402
from core.knowledge_graph import KnowledgeGraph  # noqa: E402


def _event(
    event_id: str,
    mitre_techniques: list[str],
    description: str = "Multiple Windows logon failures",
) -> EventRecord:
    return EventRecord(
        id=event_id,
        timestamp="2026-06-08T14:22:31.000Z",
        source="wazuh",
        rule_id="60122",
        description=description,
        host="windows-endpoint-01",
        mitre_techniques=mitre_techniques,
        severity="high",
    )


def test_ingest_event_records_adds_events_techniques_and_relationships() -> None:
    graph, summary = ingest_event_records([
        _event("1700000000.12345", ["T1110", "T1078"]),
    ])

    assert summary == {
        "events_added": 1,
        "techniques_added": 2,
        "relationships_added": 2,
        "duplicates_skipped": 0,
        "events_without_mitre": 0,
    }
    assert "event:1700000000.12345" in graph.nodes
    assert "mitre:T1110" in graph.nodes
    assert "mitre:T1078" in graph.nodes
    assert "event:1700000000.12345:relates_to:mitre:T1110" in graph.relationships
    assert "event:1700000000.12345:relates_to:mitre:T1078" in graph.relationships


def test_ingest_event_records_deduplicates_events_techniques_and_relationships() -> None:
    graph = KnowledgeGraph()
    events = [
        _event("1700000000.12345", ["T1110"]),
        _event("1700000000.12345", ["T1110"]),
    ]

    _, first_summary = ingest_event_records(events, graph)
    _, second_summary = ingest_event_records(events, graph)

    assert first_summary == {
        "events_added": 1,
        "techniques_added": 1,
        "relationships_added": 1,
        "duplicates_skipped": 3,
        "events_without_mitre": 0,
    }
    assert second_summary == {
        "events_added": 0,
        "techniques_added": 0,
        "relationships_added": 0,
        "duplicates_skipped": 6,
        "events_without_mitre": 0,
    }
    assert graph.summary()["total_nodes"] == 2
    assert graph.summary()["total_relationships"] == 1


def test_ingest_event_records_counts_events_without_mitre() -> None:
    graph, summary = ingest_event_records([
        _event("1700000002.111", [], "Generic Wazuh alert without MITRE mapping"),
    ])

    assert summary["events_added"] == 1
    assert summary["techniques_added"] == 0
    assert summary["relationships_added"] == 0
    assert summary["events_without_mitre"] == 1
    assert graph.nodes["event:1700000002.111"].label == (
        "Generic Wazuh alert without MITRE mapping"
    )


def test_ingest_event_records_can_add_to_existing_graph() -> None:
    graph = KnowledgeGraph()
    graph.add_node("mitre:T1110", "MITRE Technique", "T1110")

    updated_graph, summary = ingest_event_records([
        _event("1700000000.12345", ["T1110", "T1078"]),
    ], graph)

    assert updated_graph is graph
    assert summary["events_added"] == 1
    assert summary["techniques_added"] == 1
    assert summary["relationships_added"] == 2
    assert summary["duplicates_skipped"] == 1


def test_save_graph_ingest_output_persists_summary(tmp_path: Path) -> None:
    output_path = tmp_path / "real-data-graph-ingest-output.json"
    output = save_graph_ingest_output(
        {
            "events_added": 1,
            "techniques_added": 1,
            "relationships_added": 1,
            "duplicates_skipped": 0,
            "events_without_mitre": 0,
        },
        output_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload == output
    assert payload["schema_version"] == "1.0"
    assert payload["summary"]["events_added"] == 1
    assert payload["explanation"]


def test_committed_sample_graph_ingest_output_loads() -> None:
    output = generate_sample_graph_ingest_output(
        REPOSITORY_ROOT / "reports" / "real-data-graph-ingest-output.json"
    )
    payload = json.loads(
        (REPOSITORY_ROOT / "reports" / "real-data-graph-ingest-output.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload == output
    assert payload["summary"]["events_added"] == 3
    assert payload["summary"]["techniques_added"] == 2
    assert payload["summary"]["relationships_added"] == 3
    assert payload["summary"]["events_without_mitre"] == 1
