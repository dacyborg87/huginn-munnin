"""SOC health metrics derived from canonical event bus history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean
from typing import Any

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


@dataclass(frozen=True)
class SocHealthReport:
    detection_coverage: dict[str, Any]
    false_positive_indicators: dict[str, Any]
    playbook_success_rate: dict[str, Any]
    mean_detection_to_response_time: dict[str, Any]
    generated_from: dict[str, int]
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detection_coverage": self.detection_coverage,
            "false_positive_indicators": self.false_positive_indicators,
            "playbook_success_rate": self.playbook_success_rate,
            "mean_detection_to_response_time": self.mean_detection_to_response_time,
            "generated_from": self.generated_from,
            "recommendations": self.recommendations,
        }


class MetricsEngine:
    """Compute SOC metrics using event bus data and outcome memory only."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def generate_health_report(self, persist: bool = True) -> SocHealthReport:
        events = self.event_bus.load_event_history()
        outcomes = self.event_bus.load_detection_outcomes()
        lab_events = self._filter_events(events, "lab.event")
        detection_events = self._filter_events(events, "detection.alert")
        playbook_events = self._filter_events(events, "playbook.selected")

        report = SocHealthReport(
            detection_coverage=self._compute_detection_coverage(lab_events, detection_events),
            false_positive_indicators=self._compute_false_positive_indicators(outcomes),
            playbook_success_rate=self._compute_playbook_success_rate(outcomes),
            mean_detection_to_response_time=self._compute_mean_detection_to_response_time(
                detection_events,
                playbook_events,
            ),
            generated_from={
                "lab_events": len(lab_events),
                "detection_events": len(detection_events),
                "playbook_events": len(playbook_events),
                "outcomes": len(outcomes),
            },
            recommendations=[],
        )
        report = self._with_recommendations(report)

        if persist:
            self._persist_report(report)
            self._emit_metrics_event(report)

        return report

    def _compute_detection_coverage(
        self,
        lab_events: list[dict[str, Any]],
        detection_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lab_techniques = self._technique_counts(lab_events)
        detection_techniques = self._technique_counts(detection_events)

        covered = sorted(
            technique for technique in lab_techniques if detection_techniques.get(technique, 0) > 0
        )
        missed = sorted(technique for technique in lab_techniques if technique not in covered)
        total = len(lab_techniques)

        return {
            "coverage_ratio": round(len(covered) / total, 4) if total else None,
            "covered_techniques": covered,
            "missed_techniques": missed,
            "lab_technique_counts": lab_techniques,
            "detection_technique_counts": detection_techniques,
        }

    def _compute_false_positive_indicators(self, outcomes: list[dict[str, Any]]) -> dict[str, Any]:
        flagged = [
            outcome for outcome in outcomes if self._looks_like_false_positive(outcome)
        ]
        by_detection: dict[str, int] = {}
        for outcome in flagged:
            detection_name = str(outcome.get("detection_name", "unknown"))
            by_detection[detection_name] = by_detection.get(detection_name, 0) + 1

        total = len(outcomes)
        return {
            "false_positive_count": len(flagged),
            "false_positive_ratio": round(len(flagged) / total, 4) if total else None,
            "by_detection": by_detection,
        }

    def _compute_playbook_success_rate(self, outcomes: list[dict[str, Any]]) -> dict[str, Any]:
        by_playbook: dict[str, dict[str, int | float | None]] = {}
        for outcome in outcomes:
            playbook = str(outcome.get("selected_playbook", "unknown"))
            bucket = by_playbook.setdefault(playbook, {"success": 0, "failure": 0, "partial": 0, "total": 0})
            result = str(outcome.get("outcome", "")).lower()
            bucket["total"] = int(bucket["total"] or 0) + 1
            if result in {"success", "successful", "resolved"}:
                bucket["success"] = int(bucket["success"] or 0) + 1
            elif result in {"partial", "partially_resolved"}:
                bucket["partial"] = int(bucket["partial"] or 0) + 1
            else:
                bucket["failure"] = int(bucket["failure"] or 0) + 1

        for bucket in by_playbook.values():
            total = int(bucket["total"] or 0)
            bucket["success_rate"] = round(int(bucket["success"] or 0) / total, 4) if total else None

        return {"by_playbook": by_playbook}

    def _compute_mean_detection_to_response_time(
        self,
        detection_events: list[dict[str, Any]],
        playbook_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        detection_timestamps = {
            event.get("event_id"): self._parse_timestamp(str(event.get("timestamp", "")))
            for event in detection_events
        }

        response_seconds: list[float] = []
        for event in playbook_events:
            source_event_id = event.get("raw_payload", {}).get("source_event_id")
            detection_time = detection_timestamps.get(source_event_id)
            response_time = self._parse_timestamp(str(event.get("timestamp", "")))
            if detection_time and response_time:
                response_seconds.append((response_time - detection_time).total_seconds())

        return {
            "seconds": round(mean(response_seconds), 4) if response_seconds else None,
            "sample_size": len(response_seconds),
        }

    def _with_recommendations(self, report: SocHealthReport) -> SocHealthReport:
        recommendations: list[str] = []
        coverage_ratio = report.detection_coverage.get("coverage_ratio")
        false_positive_ratio = report.false_positive_indicators.get("false_positive_ratio")

        if coverage_ratio is not None and coverage_ratio < 0.8:
            recommendations.append("Review missed lab techniques and create manually approved detection backlog.")
        if false_positive_ratio is not None and false_positive_ratio > 0.2:
            recommendations.append("Review false-positive-heavy detections for scoping or threshold tuning.")
        if report.mean_detection_to_response_time.get("seconds") is None:
            recommendations.append("Add response outcome events to measure detection-to-response time.")

        return SocHealthReport(
            detection_coverage=report.detection_coverage,
            false_positive_indicators=report.false_positive_indicators,
            playbook_success_rate=report.playbook_success_rate,
            mean_detection_to_response_time=report.mean_detection_to_response_time,
            generated_from=report.generated_from,
            recommendations=recommendations,
        )

    def _persist_report(self, report: SocHealthReport) -> None:
        report_path = self.event_bus.repository_root / "reports" / "soc-health-report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def _emit_metrics_event(self, report: SocHealthReport) -> None:
        event = SocEvent(
            event_type=SocEventType.METRICS_REPORT_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/soc-health-report.json"},
            normalized_context={
                "coverage_ratio": report.detection_coverage.get("coverage_ratio"),
                "false_positive_ratio": report.false_positive_indicators.get("false_positive_ratio"),
                "mean_detection_to_response_seconds": report.mean_detection_to_response_time.get("seconds"),
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

    @staticmethod
    def _looks_like_false_positive(outcome: dict[str, Any]) -> bool:
        result = str(outcome.get("outcome", "")).lower()
        notes = str(outcome.get("analyst_notes", "")).lower()
        return result in {"false_positive", "fp"} or "false positive" in notes

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
