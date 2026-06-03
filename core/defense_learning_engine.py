"""Defensive learning insights from SOC intelligence reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType
from core.strategic_memory import StrategicMemory


@dataclass(frozen=True)
class LearningInsight:
    insight_id: str
    insight_type: str
    severity: str
    title: str
    evidence: dict[str, Any]
    recommendation: str
    status: str = "recommendation_only"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "insight_type": self.insight_type,
            "severity": self.severity,
            "title": self.title,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "status": self.status,
            "timestamp": self.timestamp,
        }


class DefenseLearningEngine:
    """Extract structural defensive learning from event-derived reports."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def learn(self, persist: bool = True) -> list[LearningInsight]:
        attack_success = self._read_report("attack-success-probability.json", default=[])
        defense_plan = self._read_report("defense-plan.json", default={})
        coverage = self._read_report("coverage-matrix.json", default=[])
        strategic_memory = [pattern.to_dict() for pattern in StrategicMemory(self.event_bus).update()]
        insights = [
            *self._risk_insights(attack_success),
            *self._coverage_insights(coverage),
            *self._decision_insights(defense_plan),
            *self._memory_insights(strategic_memory),
        ]

        if persist:
            self._persist(insights)
            self._emit_event(insights)

        return insights

    def _risk_insights(self, attack_success: list[dict[str, Any]]) -> list[LearningInsight]:
        insights: list[LearningInsight] = []
        for estimate in attack_success:
            risk_score = int(estimate.get("risk_score", 0))
            if risk_score < 55:
                continue
            evidence = estimate.get("evidence", {})
            insights.append(
                LearningInsight(
                    insight_id=str(uuid4()),
                    insight_type="high_chain_success_risk",
                    severity="critical" if risk_score >= 75 else "high",
                    title=f"Attack chain {estimate.get('chain_id', 'unknown')} retains high success probability",
                    evidence={
                        "risk_score": risk_score,
                        "probability": estimate.get("probability"),
                        "detection_gap_factor": estimate.get("detection_gap_factor"),
                        "response_weakness_factor": estimate.get("response_weakness_factor"),
                        "telemetry_blind_spot_factor": estimate.get("telemetry_blind_spot_factor"),
                        "undetected_techniques": evidence.get("undetected_techniques", []),
                    },
                    recommendation=(
                        "Prioritize chain-disrupting visibility and response improvements before adding "
                        "lower-impact detections."
                    ),
                )
            )
        return insights

    def _coverage_insights(self, coverage: list[dict[str, Any]]) -> list[LearningInsight]:
        blind_spots = [
            row for row in coverage if not row.get("detected", False)
        ]
        weak_response = [
            row for row in coverage if row.get("response_coverage_effectiveness") in {"none", "weak"}
        ]
        insights: list[LearningInsight] = []

        if blind_spots:
            insights.append(
                LearningInsight(
                    insight_id=str(uuid4()),
                    insight_type="telemetry_blind_spot_cluster",
                    severity="high",
                    title="Undetected techniques form a telemetry blind-spot cluster",
                    evidence={
                        "techniques": [row.get("technique_id") for row in blind_spots],
                        "count": len(blind_spots),
                    },
                    recommendation=(
                        "Treat these as coverage backlog items requiring analyst review and evidence mapping."
                    ),
                )
            )

        if weak_response:
            insights.append(
                LearningInsight(
                    insight_id=str(uuid4()),
                    insight_type="response_coverage_failure",
                    severity="medium",
                    title="Some observed techniques have weak or missing response coverage",
                    evidence={
                        "techniques": [row.get("technique_id") for row in weak_response],
                        "count": len(weak_response),
                    },
                    recommendation="Improve playbook coverage or response mapping for affected techniques.",
                )
            )
        return insights

    def _decision_insights(self, defense_plan: dict[str, Any]) -> list[LearningInsight]:
        actions = defense_plan.get("prioritized_actions", [])
        backlog_actions = [
            action for action in actions if action.get("action_type") == "add_detection_backlog_item"
        ]
        if not backlog_actions:
            return []
        return [
            LearningInsight(
                insight_id=str(uuid4()),
                insight_type="structural_detection_backlog",
                severity="high",
                title="Defensive plan is dominated by missing detection backlog items",
                evidence={
                    "backlog_action_count": len(backlog_actions),
                    "techniques": [action.get("technique_id") for action in backlog_actions],
                },
                recommendation=(
                    "Address repeated visibility gaps before optimizing already-detected stages."
                ),
            )
        ]

    def _memory_insights(self, strategic_memory: list[dict[str, Any]]) -> list[LearningInsight]:
        recurring = [
            pattern for pattern in strategic_memory if pattern.get("pattern_type") == "recurring_phase_weakness"
        ]
        return [
            LearningInsight(
                insight_id=str(uuid4()),
                insight_type="recurring_structural_failure",
                severity="high",
                title=f"Recurring weakness pattern observed in {pattern.get('key')}",
                evidence={
                    "occurrence_count": pattern.get("occurrence_count"),
                    "related_techniques": pattern.get("related_techniques", []),
                    "failure_modes": pattern.get("failure_modes", []),
                },
                recommendation=pattern.get("recommended_focus", "Review strategic memory pattern."),
            )
            for pattern in recurring
        ]

    def _read_report(self, filename: str, default: Any) -> Any:
        path = self.event_bus.repository_root / "reports" / filename
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _persist(self, insights: list[LearningInsight]) -> None:
        path = self.event_bus.repository_root / "reports" / "defense-learning-insights.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([insight.to_dict() for insight in insights], indent=2, sort_keys=True),
            encoding="utf-8",
        )

        memory_path = self.event_bus.repository_root / "core" / "patterns" / "defense-learning-insights.jsonl"
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        with memory_path.open("a", encoding="utf-8") as destination:
            for insight in insights:
                destination.write(json.dumps(insight.to_dict(), sort_keys=True) + "\n")

    def _emit_event(self, insights: list[LearningInsight]) -> None:
        event = SocEvent(
            event_type=SocEventType.DEFENSE_LEARNING_INSIGHTS_CREATED,
            source_system=EventSource.MUNINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/defense-learning-insights.json"},
            normalized_context={
                "insight_count": len(insights),
                "critical_count": sum(1 for insight in insights if insight.severity == "critical"),
                "high_count": sum(1 for insight in insights if insight.severity == "high"),
            },
        )
        self.event_bus.emit(event)
