"""Attack chain reasoning from canonical SOC event bus history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


PHASE_BY_TECHNIQUE: dict[str, str] = {
    "T1046": "recon",
    "T1595": "recon",
    "T1059": "execution",
    "T1204": "execution",
    "T1110": "credential_access",
    "T1078": "post-auth",
    "T1087": "post-auth",
    "T1053": "persistence",
    "T1547": "persistence",
}

PHASE_ORDER = {
    "recon": 1,
    "execution": 2,
    "credential_access": 3,
    "persistence": 4,
    "post-auth": 5,
    "unknown": 99,
}


@dataclass(frozen=True)
class AttackChainStep:
    sequence: int
    technique_id: str
    technique_name: str
    tactic: str
    phase: str
    event_id: str
    event_type: str
    detected: bool
    response_routed: bool
    timestamp: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "tactic": self.tactic,
            "phase": self.phase,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "detected": self.detected,
            "response_routed": self.response_routed,
            "timestamp": self.timestamp,
            "context": self.context,
        }


@dataclass(frozen=True)
class AttackChainReport:
    chain_id: str
    steps: list[AttackChainStep]
    phase_sequence: list[str]
    technique_sequence: list[str]
    missing_transitions: list[dict[str, Any]]
    detected_techniques: list[str]
    undetected_techniques: list[str]
    chain_severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "steps": [step.to_dict() for step in self.steps],
            "phase_sequence": self.phase_sequence,
            "technique_sequence": self.technique_sequence,
            "missing_transitions": self.missing_transitions,
            "detected_techniques": self.detected_techniques,
            "undetected_techniques": self.undetected_techniques,
            "chain_severity": self.chain_severity,
        }


class AttackChainAnalyzer:
    """Reconstruct MITRE technique chains from event bus data."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def analyze(self, persist: bool = True) -> list[AttackChainReport]:
        events = sorted(
            self.event_bus.load_event_history(),
            key=lambda event: str(event.get("timestamp", "")),
        )
        detection_events = self._filter_events(events, "detection.alert")
        playbook_events = self._filter_events(events, "playbook.selected")
        response_by_detection = {
            str(event.get("raw_payload", {}).get("source_event_id", "")): event
            for event in playbook_events
        }

        reports: list[AttackChainReport] = []
        for chain_id, lab_events in self._group_lab_events(events).items():
            reports.append(
                self._build_lab_chain_report(
                    chain_id,
                    lab_events,
                    detection_events,
                    response_by_detection,
                )
            )

        if not reports and detection_events:
            reports.append(
                self._build_detection_only_report(
                    "observed-detections",
                    detection_events,
                    response_by_detection,
                )
            )

        if persist:
            self._persist_reports(reports)
            self._emit_report_event(reports)

        return reports

    def _build_lab_chain_report(
        self,
        chain_id: str,
        lab_events: list[dict[str, Any]],
        detection_events: list[dict[str, Any]],
        response_by_detection: dict[str, dict[str, Any]],
    ) -> AttackChainReport:
        detected_techniques = set(self._technique_sequence(detection_events))
        detection_event_ids_by_technique = self._event_ids_by_technique(detection_events)
        steps: list[AttackChainStep] = []

        for index, event in enumerate(lab_events, start=1):
            mapping = self._first_mapping(event)
            technique_id = mapping.get("technique_id", "")
            detection_ids = detection_event_ids_by_technique.get(technique_id, [])
            response_routed = any(detection_id in response_by_detection for detection_id in detection_ids)
            steps.append(
                AttackChainStep(
                    sequence=index,
                    technique_id=technique_id,
                    technique_name=mapping.get("technique_name", ""),
                    tactic=mapping.get("tactic", ""),
                    phase=self._classify_phase(technique_id, mapping.get("tactic", "")),
                    event_id=str(event.get("event_id", "")),
                    event_type=str(event.get("event_type", "")),
                    detected=technique_id in detected_techniques,
                    response_routed=response_routed,
                    timestamp=str(event.get("timestamp", "")),
                    context=dict(event.get("normalized_context", {})),
                )
            )

        return self._finalize_report(chain_id, steps)

    def _build_detection_only_report(
        self,
        chain_id: str,
        detection_events: list[dict[str, Any]],
        response_by_detection: dict[str, dict[str, Any]],
    ) -> AttackChainReport:
        steps: list[AttackChainStep] = []
        for index, event in enumerate(detection_events, start=1):
            mapping = self._first_mapping(event)
            technique_id = mapping.get("technique_id", "")
            steps.append(
                AttackChainStep(
                    sequence=index,
                    technique_id=technique_id,
                    technique_name=mapping.get("technique_name", ""),
                    tactic=mapping.get("tactic", ""),
                    phase=self._classify_phase(technique_id, mapping.get("tactic", "")),
                    event_id=str(event.get("event_id", "")),
                    event_type=str(event.get("event_type", "")),
                    detected=True,
                    response_routed=str(event.get("event_id", "")) in response_by_detection,
                    timestamp=str(event.get("timestamp", "")),
                    context=dict(event.get("normalized_context", {})),
                )
            )
        return self._finalize_report(chain_id, steps)

    def _finalize_report(self, chain_id: str, steps: list[AttackChainStep]) -> AttackChainReport:
        phase_sequence = [step.phase for step in steps]
        technique_sequence = [step.technique_id for step in steps if step.technique_id]
        detected = sorted({step.technique_id for step in steps if step.technique_id and step.detected})
        undetected = sorted({step.technique_id for step in steps if step.technique_id and not step.detected})

        return AttackChainReport(
            chain_id=chain_id,
            steps=steps,
            phase_sequence=phase_sequence,
            technique_sequence=technique_sequence,
            missing_transitions=self._detect_missing_transitions(steps),
            detected_techniques=detected,
            undetected_techniques=undetected,
            chain_severity=self._score_chain_severity(steps),
        )

    def _detect_missing_transitions(self, steps: list[AttackChainStep]) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for previous, current in zip(steps, steps[1:], strict=False):
            if previous.detected and current.detected:
                continue

            phase_progressed = PHASE_ORDER.get(current.phase, 99) >= PHASE_ORDER.get(previous.phase, 99)
            if not phase_progressed:
                continue

            missing.append(
                {
                    "from_phase": previous.phase,
                    "from_technique": previous.technique_id,
                    "to_phase": current.phase,
                    "to_technique": current.technique_id,
                    "reason": "One or both adjacent chain stages lack detection coverage.",
                    "detected_transition": previous.detected and current.detected,
                }
            )
        return missing

    def _score_chain_severity(self, steps: list[AttackChainStep]) -> str:
        phases = {step.phase for step in steps}
        if "post-auth" in phases and any(not step.detected for step in steps):
            return "critical"
        if "credential_access" in phases:
            return "high"
        if "execution" in phases or "persistence" in phases:
            return "high"
        if len(steps) >= 2:
            return "medium"
        return "low"

    def _persist_reports(self, reports: list[AttackChainReport]) -> None:
        report_path = self.event_bus.repository_root / "reports" / "attack-chain-analysis.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps([report.to_dict() for report in reports], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_report_event(self, reports: list[AttackChainReport]) -> None:
        event = SocEvent(
            event_type=SocEventType.ATTACK_CHAIN_REPORT_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/attack-chain-analysis.json"},
            normalized_context={
                "chain_count": len(reports),
                "critical_chain_count": sum(1 for report in reports if report.chain_severity == "critical"),
            },
        )
        self.event_bus.emit(event)

    def _group_lab_events(self, events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        chains: dict[str, list[dict[str, Any]]] = {}
        for event in self._filter_events(events, "lab.event"):
            context = event.get("normalized_context", {})
            chain_id = str(context.get("lab_id") or "lab-chain")
            chains.setdefault(chain_id, []).append(event)
        return chains

    @staticmethod
    def _filter_events(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
        return [event for event in events if event.get("event_type") == event_type]

    @staticmethod
    def _first_mapping(event: dict[str, Any]) -> dict[str, str]:
        mappings = event.get("mitre_mapping", [])
        if not mappings:
            return {"tactic": "", "technique_id": "", "technique_name": ""}
        return mappings[0]

    @staticmethod
    def _technique_sequence(events: list[dict[str, Any]]) -> list[str]:
        sequence: list[str] = []
        for event in events:
            for mapping in event.get("mitre_mapping", []):
                technique_id = str(mapping.get("technique_id", "")).strip()
                if technique_id:
                    sequence.append(technique_id)
        return sequence

    @staticmethod
    def _event_ids_by_technique(events: list[dict[str, Any]]) -> dict[str, list[str]]:
        event_ids: dict[str, list[str]] = {}
        for event in events:
            event_id = str(event.get("event_id", ""))
            for mapping in event.get("mitre_mapping", []):
                technique_id = str(mapping.get("technique_id", "")).strip()
                if technique_id:
                    event_ids.setdefault(technique_id, []).append(event_id)
        return event_ids

    @staticmethod
    def _classify_phase(technique_id: str, tactic: str) -> str:
        if technique_id in PHASE_BY_TECHNIQUE:
            return PHASE_BY_TECHNIQUE[technique_id]

        tactic_lower = tactic.lower()
        if "discovery" in tactic_lower:
            return "recon"
        if "execution" in tactic_lower:
            return "execution"
        if "persistence" in tactic_lower:
            return "persistence"
        if "credential" in tactic_lower:
            return "credential_access"
        if "lateral movement" in tactic_lower or "defense evasion" in tactic_lower:
            return "post-auth"
        return "unknown"

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
