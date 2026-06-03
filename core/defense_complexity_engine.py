"""Evaluate defensive architecture complexity versus coverage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


@dataclass(frozen=True)
class ComplexityInsight:
    insight_id: str
    insight_type: str
    severity: str
    title: str
    evidence: dict[str, Any]
    simplification_opportunity: str
    status: str = "recommendation_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "insight_type": self.insight_type,
            "severity": self.severity,
            "title": self.title,
            "evidence": self.evidence,
            "simplification_opportunity": self.simplification_opportunity,
            "status": self.status,
        }


class DefenseComplexityEngine:
    """Identify complexity, overlap, and simplification opportunities."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def analyze(self, persist: bool = True) -> list[ComplexityInsight]:
        coverage = self._read_report("coverage-matrix.json", default=[])
        design = self._read_report("defense-design-recommendations.json", default=[])
        event_history = self.event_bus.load_event_history()
        insights = [
            *self._overlap_insights(coverage),
            *self._complexity_without_coverage_insights(design, coverage),
            *self._event_layer_complexity_insights(event_history),
        ]

        if persist:
            self._persist(insights)
            self._emit_event(insights)

        return insights

    def _overlap_insights(self, coverage: list[dict[str, Any]]) -> list[ComplexityInsight]:
        by_tactic: dict[str, list[dict[str, Any]]] = {}
        for row in coverage:
            for tactic in row.get("tactics", []):
                by_tactic.setdefault(str(tactic), []).append(row)

        insights: list[ComplexityInsight] = []
        for tactic, rows in sorted(by_tactic.items()):
            detected_rows = [row for row in rows if row.get("detected", False)]
            if len(detected_rows) <= 1:
                continue
            insights.append(
                ComplexityInsight(
                    insight_id=f"complexity.overlap.{tactic.lower().replace(' ', '_')}",
                    insight_type="coverage_overlap",
                    severity="low",
                    title=f"Multiple covered techniques exist under {tactic}",
                    evidence={
                        "tactic": tactic,
                        "techniques": [row.get("technique_id") for row in detected_rows],
                    },
                    simplification_opportunity=(
                        "Use shared correlation and reporting abstractions for this tactic instead of "
                        "duplicating independent analysis flows."
                    ),
                )
            )
        return insights

    def _complexity_without_coverage_insights(
        self,
        design: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
    ) -> list[ComplexityInsight]:
        undercovered = [
            row for row in coverage if not row.get("detected", False)
        ]
        if not undercovered or len(design) <= 1:
            return []

        return [
            ComplexityInsight(
                insight_id="complexity.design_sprawl_under_low_coverage",
                insight_type="design_sprawl_risk",
                severity="medium",
                title="Multiple new subsystems are recommended while coverage remains low",
                evidence={
                    "design_recommendation_count": len(design),
                    "undercovered_techniques": [row.get("technique_id") for row in undercovered],
                },
                simplification_opportunity=(
                    "Sequence architecture changes around one shared post-auth telemetry and correlation layer "
                    "before adding specialized subsystems."
                ),
            )
        ]

    def _event_layer_complexity_insights(self, event_history: list[dict[str, Any]]) -> list[ComplexityInsight]:
        event_types = sorted({str(event.get("event_type")) for event in event_history})
        architecture_event_types = [
            event_type
            for event_type in event_types
            if event_type.startswith(("defense.", "security_architecture", "attack_surface"))
        ]
        if len(architecture_event_types) <= 4:
            return []

        return [
            ComplexityInsight(
                insight_id="complexity.architecture_event_volume",
                insight_type="event_taxonomy_growth",
                severity="low",
                title="Architecture intelligence event taxonomy is expanding",
                evidence={
                    "architecture_event_types": architecture_event_types,
                    "count": len(architecture_event_types),
                },
                simplification_opportunity=(
                    "Group architecture intelligence events under a common dashboard view and lifecycle state."
                ),
            )
        ]

    def _read_report(self, filename: str, default: Any) -> Any:
        path = self.event_bus.repository_root / "reports" / filename
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _persist(self, insights: list[ComplexityInsight]) -> None:
        path = self.event_bus.repository_root / "reports" / "defense-complexity-insights.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([item.to_dict() for item in insights], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_event(self, insights: list[ComplexityInsight]) -> None:
        event = SocEvent(
            event_type=SocEventType.DEFENSE_COMPLEXITY_ANALYSIS_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/defense-complexity-insights.json"},
            normalized_context={
                "insight_count": len(insights),
                "medium_or_higher_count": sum(
                    1 for item in insights if item.severity in {"medium", "high", "critical"}
                ),
            },
        )
        self.event_bus.emit(event)
