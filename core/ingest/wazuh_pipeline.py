"""Orchestrate Wazuh file reading into graph ingest and evidence generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.ingest.graph_ingest import ingest_event_records
from core.ingest.real_data_evidence import build_real_data_evidence
from core.ingest.wazuh_file_reader import read_wazuh_alert_file
from core.knowledge_graph import KnowledgeGraph


DEFAULT_OUTPUT_PATH = Path("reports/real-data-pipeline-output.json")


def run_wazuh_file_pipeline(
    path: Path | str,
    *,
    persist: bool = True,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """Read a Wazuh alert file and run the small real-data intelligence pipeline."""

    read_result = read_wazuh_alert_file(path)
    graph = KnowledgeGraph()
    _, graph_summary = ingest_event_records(read_result.events, graph)
    evidence_records = build_real_data_evidence(read_result.events, graph, persist=False)
    evidence_gaps = [
        record
        for record in evidence_records
        if not record.related_entities.mitre_techniques
    ]

    summary = {
        "records_read": int(read_result.summary["records_read"]),
        "records_parsed": int(read_result.summary["records_parsed"]),
        "records_skipped": int(read_result.summary["records_skipped"]),
        "events_added": graph_summary["events_added"],
        "techniques_added": graph_summary["techniques_added"],
        "relationships_added": graph_summary["relationships_added"],
        "duplicates_skipped": graph_summary["duplicates_skipped"],
        "evidence_records_created": len(evidence_records),
        "evidence_gaps_created": len(evidence_gaps),
    }
    output = {
        "schema_version": "1.0",
        "source_path": str(path),
        "summary": summary,
        "evidence_records": [record.to_dict() for record in evidence_records],
        "explanation": (
            "The Wazuh file was read, valid alerts were normalized, events were "
            "added to a Knowledge Graph, and Evidence Layer records were generated."
        ),
    }
    if "error" in read_result.summary:
        output["error"] = read_result.summary["error"]

    if persist:
        _save_output(output, output_path)
    return output


def generate_sample_wazuh_pipeline_output(
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    sample_input = Path("reports/sample-wazuh-pipeline-alerts.json")
    sample_input.parent.mkdir(parents=True, exist_ok=True)
    sample_input.write_text(
        json.dumps(
            [
                {
                    "id": "1700000000.12345",
                    "timestamp": "2026-06-08T14:22:31.000Z",
                    "agent": {"name": "windows-endpoint-01"},
                    "rule": {
                        "id": "60122",
                        "level": 10,
                        "description": "Multiple Windows logon failures",
                        "mitre": {"id": ["T1110", "T1078"]},
                    },
                },
                {
                    "id": "1700000002.111",
                    "timestamp": "2026-06-08T15:15:00.000Z",
                    "agent": {"name": "linux-web-01"},
                    "rule": {
                        "id": "1002",
                        "level": 5,
                        "description": "Generic Wazuh alert without MITRE mapping",
                    },
                },
                "malformed alert",
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        return run_wazuh_file_pipeline(sample_input, persist=True, output_path=output_path)
    finally:
        sample_input.unlink(missing_ok=True)


def _save_output(output: dict[str, Any], path: Path | str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True),
        encoding="utf-8",
    )
