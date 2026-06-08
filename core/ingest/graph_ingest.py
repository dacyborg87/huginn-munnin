"""Add normalized real-data events into the Knowledge Graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.ingest.wazuh_parser import EventRecord
from core.knowledge_graph import KnowledgeGraph


DEFAULT_OUTPUT_PATH = Path("reports/real-data-graph-ingest-output.json")


def ingest_event_records(
    events: list[EventRecord],
    graph: KnowledgeGraph | None = None,
) -> tuple[KnowledgeGraph, dict[str, int]]:
    """Add normalized EventRecord objects into a KnowledgeGraph."""

    target_graph = graph or KnowledgeGraph()
    summary = {
        "events_added": 0,
        "techniques_added": 0,
        "relationships_added": 0,
        "duplicates_skipped": 0,
        "events_without_mitre": 0,
    }

    for index, event in enumerate(events):
        event_node_id = _event_node_id(event, index)
        if event_node_id in target_graph.nodes:
            summary["duplicates_skipped"] += 1
        else:
            target_graph.add_node(
                event_node_id,
                "Event",
                event.description or "wazuh.alert",
                {
                    "source_system": event.source,
                    "timestamp": event.timestamp,
                    "rule_id": event.rule_id,
                    "host": event.host,
                    "severity": event.severity,
                },
            )
            summary["events_added"] += 1

        if not event.mitre_techniques:
            summary["events_without_mitre"] += 1
            continue

        for technique_id in event.mitre_techniques:
            technique_node_id = _technique_node_id(technique_id)
            if technique_node_id in target_graph.nodes:
                summary["duplicates_skipped"] += 1
            else:
                target_graph.add_node(
                    technique_node_id,
                    "MITRE Technique",
                    technique_id,
                    {"technique_id": technique_id},
                )
                summary["techniques_added"] += 1

            relationship_id = f"{event_node_id}:relates_to:{technique_node_id}"
            if relationship_id in target_graph.relationships:
                summary["duplicates_skipped"] += 1
            else:
                target_graph.add_relationship(
                    event_node_id,
                    "relates_to",
                    technique_node_id,
                    {"source": "real_data_ingest"},
                )
                summary["relationships_added"] += 1

    return target_graph, summary


def save_graph_ingest_output(
    summary: dict[str, int],
    path: Path | str = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    output = {
        "schema_version": "1.0",
        "summary": summary,
        "explanation": (
            "Normalized real-data events were added to the Knowledge Graph as "
            "Event nodes and related to MITRE Technique nodes when techniques "
            "were present."
        ),
    }
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


def generate_sample_graph_ingest_output(
    path: Path | str = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    sample_events = [
        EventRecord(
            id="1700000000.12345",
            timestamp="2026-06-08T14:22:31.000Z",
            source="wazuh",
            rule_id="60122",
            description="Multiple Windows logon failures",
            host="windows-endpoint-01",
            mitre_techniques=["T1110", "T1078"],
            severity="high",
        ),
        EventRecord(
            id="1700000001.999",
            timestamp="2026-06-08T15:10:05.000Z",
            source="wazuh",
            rule_id="5710",
            description="sshd brute force trying to get access",
            host="linux-web-01",
            mitre_techniques=["T1110"],
            severity="critical",
        ),
        EventRecord(
            id="1700000002.111",
            timestamp="2026-06-08T15:15:00.000Z",
            source="wazuh",
            rule_id="1002",
            description="Generic Wazuh alert without MITRE mapping",
            host="linux-web-01",
            mitre_techniques=[],
            severity="medium",
        ),
    ]
    _, summary = ingest_event_records(sample_events)
    return save_graph_ingest_output(summary, path)


def _event_node_id(event: EventRecord, index: int) -> str:
    if event.id:
        return event.id if event.id.startswith("event:") else f"event:{event.id}"
    return f"event:missing-id:{index}"


def _technique_node_id(technique_id: str) -> str:
    return technique_id if technique_id.startswith("mitre:") else f"mitre:{technique_id}"
