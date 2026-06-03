"""MITRE coverage matrix derived from SOC event bus history."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.attack_chain_analyzer import AttackChainAnalyzer
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


@dataclass(frozen=True)
class TechniqueCoverage:
    technique_id: str
    technique_name: str
    tactics: list[str]
    detected: bool
    correlated_across_chain: bool
    response_coverage_effectiveness: str
    detection_count: int
    lab_count: int
    playbook_count: int
    outcome_summary: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "tactics": self.tactics,
            "detected": self.detected,
            "correlated_across_chain": self.correlated_across_chain,
            "response_coverage_effectiveness": self.response_coverage_effectiveness,
            "detection_count": self.detection_count,
            "lab_count": self.lab_count,
            "playbook_count": self.playbook_count,
            "outcome_summary": self.outcome_summary,
        }


class CoverageMatrix:
    """Map observed MITRE techniques to detection, chain, and response coverage."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def build(self, persist: bool = True) -> list[TechniqueCoverage]:
        events = self.event_bus.load_event_history()
        outcomes = self.event_bus.load_detection_outcomes()
        lab_events = self._filter_events(events, "lab.event")
        detection_events = self._filter_events(events, "detection.alert")
        playbook_events = self._filter_events(events, "playbook.selected")

        chain_reports = AttackChainAnalyzer(self.event_bus).analyze(persist=False)
        correlated_techniques = self._correlated_techniques(chain_reports)
        technique_metadata = self._technique_metadata([*lab_events, *detection_events])
        detection_counts = self._technique_counts(detection_events)
        lab_counts = self._technique_counts(lab_events)
        playbook_counts = self._playbook_counts_by_technique(playbook_events, detection_events)
        outcome_summary = self._outcome_summary_by_technique(outcomes, detection_events)

        rows: list[TechniqueCoverage] = []
        for technique_id in sorted(technique_metadata):
            outcomes_for_technique = outcome_summary.get(
                technique_id,
                {"success": 0, "partial": 0, "failure": 0, "false_positive": 0, "total": 0},
            )
            rows.append(
                TechniqueCoverage(
                    technique_id=technique_id,
                    technique_name=technique_metadata[technique_id]["technique_name"],
                    tactics=sorted(technique_metadata[technique_id]["tactics"]),
                    detected=detection_counts.get(technique_id, 0) > 0,
                    correlated_across_chain=technique_id in correlated_techniques,
                    response_coverage_effectiveness=self._response_effectiveness(outcomes_for_technique),
                    detection_count=detection_counts.get(technique_id, 0),
                    lab_count=lab_counts.get(technique_id, 0),
                    playbook_count=playbook_counts.get(technique_id, 0),
                    outcome_summary=outcomes_for_technique,
                )
            )

        if persist:
            self._persist_matrix(rows)
            self._emit_matrix_event(rows)

        return rows

    def _correlated_techniques(self, chain_reports: list[Any]) -> set[str]:
        correlated: set[str] = set()
        for report in chain_reports:
            detected_steps = [step for step in report.steps if step.detected]
            if len(detected_steps) < 2:
                continue
            for step in detected_steps:
                correlated.add(step.technique_id)
        return correlated

    def _playbook_counts_by_technique(
        self,
        playbook_events: list[dict[str, Any]],
        detection_events: list[dict[str, Any]],
    ) -> dict[str, int]:
        technique_by_detection_id = self._first_technique_by_event_id(detection_events)
        counts: dict[str, int] = {}
        for event in playbook_events:
            source_event_id = str(event.get("raw_payload", {}).get("source_event_id", ""))
            technique_id = technique_by_detection_id.get(source_event_id, "")
            if technique_id:
                counts[technique_id] = counts.get(technique_id, 0) + 1
        return counts

    def _outcome_summary_by_technique(
        self,
        outcomes: list[dict[str, Any]],
        detection_events: list[dict[str, Any]],
    ) -> dict[str, dict[str, int]]:
        technique_by_detection_id = self._first_technique_by_event_id(detection_events)
        summary: dict[str, dict[str, int]] = {}
        for outcome in outcomes:
            technique_id = technique_by_detection_id.get(str(outcome.get("source_event_id", "")), "")
            if not technique_id:
                continue
            bucket = summary.setdefault(
                technique_id,
                {"success": 0, "partial": 0, "failure": 0, "false_positive": 0, "total": 0},
            )
            bucket["total"] += 1
            result = str(outcome.get("outcome", "")).lower()
            notes = str(outcome.get("analyst_notes", "")).lower()
            if result in {"success", "successful", "resolved"}:
                bucket["success"] += 1
            elif result in {"partial", "partially_resolved"}:
                bucket["partial"] += 1
            elif result in {"false_positive", "fp"} or "false positive" in notes:
                bucket["false_positive"] += 1
            else:
                bucket["failure"] += 1
        return summary

    def _response_effectiveness(self, summary: dict[str, int]) -> str:
        total = summary.get("total", 0)
        if total == 0:
            return "none"
        if summary.get("success", 0) == total:
            return "strong"
        if summary.get("success", 0) + summary.get("partial", 0) > 0:
            return "partial"
        return "weak"

    def _persist_matrix(self, rows: list[TechniqueCoverage]) -> None:
        matrix_path = self.event_bus.repository_root / "reports" / "coverage-matrix.json"
        matrix_path.parent.mkdir(parents=True, exist_ok=True)
        matrix_path.write_text(
            json.dumps([row.to_dict() for row in rows], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_matrix_event(self, rows: list[TechniqueCoverage]) -> None:
        event = SocEvent(
            event_type=SocEventType.COVERAGE_MATRIX_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/coverage-matrix.json"},
            normalized_context={
                "technique_count": len(rows),
                "detected_count": sum(1 for row in rows if row.detected),
                "correlated_count": sum(1 for row in rows if row.correlated_across_chain),
            },
        )
        self.event_bus.emit(event)

    @staticmethod
    def _filter_events(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
        return [event for event in events if event.get("event_type") == event_type]

    @staticmethod
    def _technique_metadata(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        metadata: dict[str, dict[str, Any]] = {}
        for event in events:
            for mapping in event.get("mitre_mapping", []):
                technique_id = str(mapping.get("technique_id", "")).strip()
                if not technique_id:
                    continue
                entry = metadata.setdefault(
                    technique_id,
                    {"technique_name": str(mapping.get("technique_name", "")), "tactics": set()},
                )
                if not entry["technique_name"]:
                    entry["technique_name"] = str(mapping.get("technique_name", ""))
                tactic = str(mapping.get("tactic", "")).strip()
                if tactic:
                    entry["tactics"].add(tactic)
        return metadata

    @staticmethod
    def _technique_counts(events: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in events:
            for mapping in event.get("mitre_mapping", []):
                technique_id = str(mapping.get("technique_id", "")).strip()
                if technique_id:
                    counts[technique_id] = counts.get(technique_id, 0) + 1
        return counts

    @staticmethod
    def _first_technique_by_event_id(events: list[dict[str, Any]]) -> dict[str, str]:
        techniques: dict[str, str] = {}
        for event in events:
            event_id = str(event.get("event_id", ""))
            mappings = event.get("mitre_mapping", [])
            if event_id and mappings:
                techniques[event_id] = str(mappings[0].get("technique_id", "")).strip()
        return techniques
