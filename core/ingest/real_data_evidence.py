"""Generate Evidence Layer records from normalized real-data events."""

from __future__ import annotations

from pathlib import Path

from core.evidence_schema import (
    ConfidenceBreakdown,
    ConfidenceFactor,
    EvidenceRecord,
    EvidenceSourceType,
    RelatedEvidenceEntities,
    confidence_level_for_score,
    save_evidence_index,
)
from core.ingest.graph_ingest import ingest_event_records
from core.ingest.wazuh_parser import EventRecord
from core.knowledge_graph import KnowledgeGraph


DEFAULT_OUTPUT_PATH = Path("reports/real-data-evidence-output.json")


def build_real_data_evidence(
    events: list[EventRecord],
    graph: KnowledgeGraph | None = None,
    *,
    persist: bool = True,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
) -> list[EvidenceRecord]:
    """Build evidence records from normalized Wazuh EventRecord objects."""

    ingested_graph, _ = ingest_event_records(events, graph)
    records = [
        _evidence_for_event(event, index, ingested_graph)
        for index, event in enumerate(events)
    ]
    if persist:
        save_evidence_index(output_path, records)
    return records


def generate_sample_real_data_evidence_output(
    path: Path | str = DEFAULT_OUTPUT_PATH,
) -> list[EvidenceRecord]:
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
    return build_real_data_evidence(sample_events, persist=True, output_path=path)


def _evidence_for_event(
    event: EventRecord,
    index: int,
    graph: KnowledgeGraph,
) -> EvidenceRecord:
    event_node_id = _event_node_id(event, index)
    related_techniques = _related_techniques(event_node_id, event, graph)
    confidence = _confidence_for_event(event, related_techniques)
    is_gap = not related_techniques
    return EvidenceRecord(
        evidence_id=f"evidence:real-data-{_slug(event_node_id)}",
        title=_title_for_event(event, is_gap),
        summary=_summary_for_event(event, event_node_id, related_techniques, is_gap),
        source_type=EvidenceSourceType.DETECTION_ALERT,
        source_path="reports/real-data-graph-ingest-output.json",
        source_reference=event_node_id,
        timestamp=event.timestamp or "unknown",
        related_entities=RelatedEvidenceEntities(
            events=[event_node_id],
            mitre_techniques=related_techniques,
        ),
        confidence=confidence,
    )


def _related_techniques(
    event_node_id: str,
    event: EventRecord,
    graph: KnowledgeGraph,
) -> list[str]:
    techniques = {
        relationship.target_id
        for relationship in graph.relationships.values()
        if relationship.source_id == event_node_id
        and relationship.relationship_type == "relates_to"
        and relationship.target_id.startswith("mitre:")
    }
    techniques.update(_technique_node_id(technique) for technique in event.mitre_techniques)
    return sorted(techniques)


def _confidence_for_event(
    event: EventRecord,
    related_techniques: list[str],
) -> ConfidenceBreakdown:
    has_mitre = bool(related_techniques)
    severity_value = {
        "critical": 1.0,
        "high": 0.85,
        "medium": 0.6,
        "low": 0.35,
    }.get((event.severity or "").lower(), 0.25)
    technique_value = 1.0 if has_mitre else 0.0
    rule_value = 1.0 if event.rule_id else 0.25
    host_value = 1.0 if event.host else 0.5
    calculation = {
        "source_reliability": _factor(0.30, 1.0),
        "mitre_mapping": _factor(0.30, technique_value),
        "rule_context": _factor(0.15, rule_value),
        "host_context": _factor(0.10, host_value),
        "severity_alignment": _factor(0.15, severity_value),
    }
    score = round(sum(factor.weighted_score for factor in calculation.values()), 3)
    if not has_mitre:
        score = min(score, 0.35)
    level = confidence_level_for_score(score)
    explanation = (
        f"Confidence is {level.value} because Wazuh rule {event.rule_id or 'unknown'} "
        f"reported severity {event.severity or 'unknown'} and "
        f"{'included MITRE technique context' if has_mitre else 'did not include MITRE technique context'}."
    )
    return ConfidenceBreakdown(
        score=score,
        level=level,
        calculation=calculation,
        explanation=explanation,
    )


def _title_for_event(event: EventRecord, is_gap: bool) -> str:
    prefix = "Evidence gap for Wazuh alert" if is_gap else "Evidence for Wazuh alert"
    return f"{prefix}: {event.description or event.rule_id or event.id or 'unknown alert'}"


def _summary_for_event(
    event: EventRecord,
    event_node_id: str,
    related_techniques: list[str],
    is_gap: bool,
) -> str:
    if is_gap:
        return (
            f"{event_node_id} was parsed from Wazuh rule {event.rule_id or 'unknown'} "
            f"on host {event.host or 'unknown'} with severity {event.severity or 'unknown'}, "
            "but no MITRE techniques were available. Huginn should treat this as an "
            "evidence gap until more context is added."
        )
    return (
        f"{event_node_id} was parsed from Wazuh rule {event.rule_id or 'unknown'} "
        f"on host {event.host or 'unknown'} with severity {event.severity or 'unknown'} "
        f"and is linked to MITRE technique(s): {', '.join(related_techniques)}."
    )


def _factor(weight: float, value: float) -> ConfidenceFactor:
    return ConfidenceFactor(
        weight=weight,
        value=value,
        weighted_score=round(weight * value, 3),
    )


def _event_node_id(event: EventRecord, index: int) -> str:
    if event.id:
        return event.id if event.id.startswith("event:") else f"event:{event.id}"
    return f"event:missing-id:{index}"


def _technique_node_id(technique_id: str) -> str:
    return technique_id if technique_id.startswith("mitre:") else f"mitre:{technique_id}"


def _slug(value: str) -> str:
    return value.replace(":", "-").replace("/", "-").replace(".", "-")
