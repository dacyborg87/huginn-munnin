"""Gap analysis for SOC coverage using canonical event bus data."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


@dataclass(frozen=True)
class GapFinding:
    finding_id: str
    finding_type: str
    severity: str
    title: str
    evidence: dict[str, Any]
    recommendation: str
    status: str = "logged_only"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "finding_type": self.finding_type,
            "severity": self.severity,
            "title": self.title,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "status": self.status,
            "timestamp": self.timestamp,
        }


class GapAnalysisEngine:
    """Identify weak coverage areas without touching detection content."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus
        self.findings_path = self.event_bus.repository_root / "core" / "patterns" / "gap-findings.jsonl"

    def analyze(self, persist: bool = True) -> list[GapFinding]:
        events = self.event_bus.load_event_history()
        outcomes = self.event_bus.load_detection_outcomes()
        lab_events = self._filter_events(events, "lab.event")
        detection_events = self._filter_events(events, "detection.alert")
        findings = [
            *self._find_missed_lab_techniques(lab_events, detection_events),
            *self._find_weak_detection_coverage(lab_events, detection_events),
            *self._find_outcome_quality_gaps(outcomes),
        ]

        if persist:
            for finding in findings:
                self._persist_finding(finding)
                self._emit_gap_event(finding)

        return findings

    def _find_missed_lab_techniques(
        self,
        lab_events: list[dict[str, Any]],
        detection_events: list[dict[str, Any]],
    ) -> list[GapFinding]:
        lab_techniques = self._technique_counts(lab_events)
        detection_techniques = self._technique_counts(detection_events)

        findings: list[GapFinding] = []
        for technique_id, lab_count in sorted(lab_techniques.items()):
            if detection_techniques.get(technique_id, 0) > 0:
                continue
            findings.append(
                GapFinding(
                    finding_id=str(uuid4()),
                    finding_type="missed_lab_detection",
                    severity="high",
                    title=f"Lab activity for {technique_id} has no matching detection event",
                    evidence={
                        "technique_id": technique_id,
                        "lab_event_count": lab_count,
                        "detection_event_count": 0,
                    },
                    recommendation=(
                        "Create a manually reviewed detection engineering backlog item for this "
                        "technique. Do not auto-modify existing rules."
                    ),
                )
            )
        return findings

    def _find_weak_detection_coverage(
        self,
        lab_events: list[dict[str, Any]],
        detection_events: list[dict[str, Any]],
    ) -> list[GapFinding]:
        lab_techniques = self._technique_counts(lab_events)
        detection_techniques = self._technique_counts(detection_events)
        findings: list[GapFinding] = []

        for technique_id, lab_count in sorted(lab_techniques.items()):
            detection_count = detection_techniques.get(technique_id, 0)
            if detection_count == 0:
                continue
            coverage_ratio = detection_count / lab_count
            if coverage_ratio >= 0.5:
                continue
            findings.append(
                GapFinding(
                    finding_id=str(uuid4()),
                    finding_type="weak_detection_coverage",
                    severity="medium",
                    title=f"Weak detection coverage for {technique_id}",
                    evidence={
                        "technique_id": technique_id,
                        "lab_event_count": lab_count,
                        "detection_event_count": detection_count,
                        "coverage_ratio": round(coverage_ratio, 4),
                    },
                    recommendation=(
                        "Review telemetry prerequisites, detection thresholds, and lab evidence "
                        "before proposing rule changes."
                    ),
                )
            )
        return findings

    def _find_outcome_quality_gaps(self, outcomes: list[dict[str, Any]]) -> list[GapFinding]:
        by_detection: dict[str, dict[str, int]] = {}
        for outcome in outcomes:
            detection_name = str(outcome.get("detection_name", "unknown"))
            bucket = by_detection.setdefault(detection_name, {"total": 0, "false_positive": 0, "failure": 0})
            bucket["total"] += 1

            result = str(outcome.get("outcome", "")).lower()
            notes = str(outcome.get("analyst_notes", "")).lower()
            if result in {"false_positive", "fp"} or "false positive" in notes:
                bucket["false_positive"] += 1
            if result in {"failure", "failed"}:
                bucket["failure"] += 1

        findings: list[GapFinding] = []
        for detection_name, counts in sorted(by_detection.items()):
            total = counts["total"]
            if not total:
                continue
            false_positive_ratio = counts["false_positive"] / total
            failure_ratio = counts["failure"] / total
            if false_positive_ratio <= 0.25 and failure_ratio <= 0.25:
                continue

            findings.append(
                GapFinding(
                    finding_id=str(uuid4()),
                    finding_type="outcome_quality_gap",
                    severity="medium",
                    title=f"Outcome quality concern for {detection_name}",
                    evidence={
                        "detection_name": detection_name,
                        "total_outcomes": total,
                        "false_positive_ratio": round(false_positive_ratio, 4),
                        "failure_ratio": round(failure_ratio, 4),
                    },
                    recommendation=(
                        "Review incident reports and analyst notes for tuning candidates. "
                        "Keep suggestions in backlog until manually approved."
                    ),
                )
            )
        return findings

    def _persist_finding(self, finding: GapFinding) -> None:
        self.findings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.findings_path.open("a", encoding="utf-8") as destination:
            destination.write(json.dumps(finding.to_dict(), sort_keys=True) + "\n")

    def _emit_gap_event(self, finding: GapFinding) -> None:
        event = SocEvent(
            event_type=SocEventType.GAP_FINDING_RECORDED,
            source_system=EventSource.MUNINN,
            severity=EventSeverity.MEDIUM,
            raw_payload={"finding_id": finding.finding_id},
            normalized_context={
                "finding_type": finding.finding_type,
                "title": finding.title,
                "status": finding.status,
                "recommendation": finding.recommendation,
            },
        )
        self.event_bus.emit(event)

    @staticmethod
    def _filter_events(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
        return [event for event in events if event.get("event_type") == event_type]

    @staticmethod
    def _technique_counts(events: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in events:
            for mapping in event.get("mitre_mapping", []):
                technique_id = str(mapping.get("technique_id", "")).strip()
                if technique_id:
                    counts[technique_id] = counts.get(technique_id, 0) + 1
        return counts
