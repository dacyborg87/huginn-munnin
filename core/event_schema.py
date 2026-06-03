"""Canonical SOC event schema for Huginn/Muninn integration.

The schema intentionally stays independent from the FastAPI application package
and the detection rule files. Detection content remains sensor-only; this module
normalizes alerts and lab activity after they are produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class EventSource(StrEnum):
    WAZUH = "wazuh"
    SURICATA = "suricata"
    SYSMON = "sysmon"
    AUDITD = "auditd"
    LAB = "lab"
    PLAYBOOK = "playbook"
    REPORT = "report"
    HUGINN = "huginn"
    MUNINN = "muninn"


class EventSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SocEventType(StrEnum):
    DETECTION_ALERT = "detection.alert"
    LAB_EVENT = "lab.event"
    PLAYBOOK_SELECTED = "playbook.selected"
    RESPONSE_RECOMMENDED = "response.recommended"
    REPORT_CREATED = "report.created"
    MEMORY_FEEDBACK_RECORDED = "memory.feedback_recorded"
    METRICS_REPORT_CREATED = "metrics.report_created"
    GAP_FINDING_RECORDED = "gap.finding_recorded"
    ATTACK_CHAIN_REPORT_CREATED = "attack_chain.report_created"
    COVERAGE_MATRIX_CREATED = "coverage_matrix.created"
    PRIORITIZED_GAPS_CREATED = "gap.prioritized"
    ATTACK_SUCCESS_MODEL_CREATED = "attack_success_model.created"
    DEFENSE_PRIORITIES_CREATED = "defense.priorities_created"
    DEFENSE_PLAN_CREATED = "defense.plan_created"
    DEFENSE_LEARNING_INSIGHTS_CREATED = "defense.learning_insights_created"
    DEFENSE_EVOLUTION_METRICS_CREATED = "defense.evolution_metrics_created"
    STRATEGIC_MEMORY_UPDATED = "strategic_memory.updated"
    SECURITY_ARCHITECTURE_ANALYSIS_CREATED = "security_architecture.analysis_created"
    DEFENSE_DESIGN_RECOMMENDATIONS_CREATED = "defense_design.recommendations_created"
    ATTACK_SURFACE_MODEL_CREATED = "attack_surface.model_created"
    DEFENSE_COMPLEXITY_ANALYSIS_CREATED = "defense_complexity.analysis_created"


@dataclass(frozen=True)
class MitreMapping:
    tactic: str
    technique_id: str
    technique_name: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "tactic": self.tactic,
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
        }


@dataclass(frozen=True)
class SocEvent:
    event_type: SocEventType
    source_system: EventSource | str
    mitre_mapping: list[MitreMapping] = field(default_factory=list)
    severity: EventSeverity | str = EventSeverity.INFO
    raw_payload: dict[str, Any] = field(default_factory=dict)
    normalized_context: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        source = self.source_system.value if isinstance(self.source_system, EventSource) else self.source_system
        severity = self.severity.value if isinstance(self.severity, EventSeverity) else self.severity
        event_type = self.event_type.value

        return {
            "event_id": self.event_id,
            "event_type": event_type,
            "source_system": source,
            "mitre_mapping": [mapping.to_dict() for mapping in self.mitre_mapping],
            "severity": severity,
            "timestamp": self.timestamp,
            "raw_payload": self.raw_payload,
            "normalized_context": self.normalized_context,
        }


def normalize_mitre_mapping(raw_mapping: Any) -> list[MitreMapping]:
    if raw_mapping is None:
        return []
    if isinstance(raw_mapping, MitreMapping):
        return [raw_mapping]
    if isinstance(raw_mapping, dict):
        return [
            MitreMapping(
                tactic=str(raw_mapping.get("tactic", "")),
                technique_id=str(raw_mapping.get("technique_id", raw_mapping.get("id", ""))),
                technique_name=str(raw_mapping.get("technique_name", raw_mapping.get("name", ""))),
            )
        ]
    if isinstance(raw_mapping, list):
        mappings: list[MitreMapping] = []
        for entry in raw_mapping:
            mappings.extend(normalize_mitre_mapping(entry))
        return mappings
    return []
