"""Defensive decision-making engine for SOC intelligence outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.attack_chain_analyzer import AttackChainAnalyzer
from core.attack_success_model import AttackSuccessModel
from core.coverage_matrix import CoverageMatrix
from core.defense_prioritizer import DefensePrioritizer
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType
from core.gap_prioritizer import GapPrioritizer


@dataclass(frozen=True)
class DefensiveActionPlan:
    plan_id: str
    objective: str
    chain_risk_summary: list[dict[str, Any]]
    prioritized_actions: list[dict[str, Any]]
    chain_disruption_strategy: list[dict[str, Any]]
    guardrails: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "objective": self.objective,
            "chain_risk_summary": self.chain_risk_summary,
            "prioritized_actions": self.prioritized_actions,
            "chain_disruption_strategy": self.chain_disruption_strategy,
            "guardrails": self.guardrails,
        }


class DefenseDecisionEngine:
    """Assemble defensive action plans from event-derived intelligence reports."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def create_plan(self, persist: bool = True) -> DefensiveActionPlan:
        chains = self._load_or_build_chains()
        coverage = self._load_or_build_coverage()
        gaps = self._load_or_build_gaps()
        attack_success = [estimate.to_dict() for estimate in AttackSuccessModel(self.event_bus).estimate()]
        priorities = [action.to_dict() for action in DefensePrioritizer(self.event_bus).prioritize()]

        plan = DefensiveActionPlan(
            plan_id="defense-plan.current",
            objective="Disrupt the most probable successful attack chain with analyst-approved defensive improvements.",
            chain_risk_summary=self._chain_risk_summary(chains, attack_success),
            prioritized_actions=priorities,
            chain_disruption_strategy=self._chain_disruption_strategy(priorities, coverage, gaps),
            guardrails=[
                "Do not modify detection rules automatically.",
                "Do not modify lab configurations.",
                "Route all rule and telemetry recommendations through analyst review.",
                "Use reports and pattern memory as decision support, not autonomous enforcement.",
            ],
        )

        if persist:
            self._persist(plan)
            self._emit_event(plan)

        return plan

    def _chain_risk_summary(
        self,
        chains: list[dict[str, Any]],
        attack_success: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        success_by_chain = {estimate["chain_id"]: estimate for estimate in attack_success}
        summary: list[dict[str, Any]] = []
        for chain in chains:
            estimate = success_by_chain.get(str(chain.get("chain_id", "")), {})
            summary.append(
                {
                    "chain_id": chain.get("chain_id", "unknown"),
                    "chain_severity": chain.get("chain_severity", "low"),
                    "attack_success_probability": estimate.get("probability"),
                    "risk_score": estimate.get("risk_score"),
                    "risk_level": estimate.get("risk_level"),
                    "detected_techniques": chain.get("detected_techniques", []),
                    "undetected_techniques": chain.get("undetected_techniques", []),
                    "missing_transition_count": len(chain.get("missing_transitions", [])),
                }
            )
        return summary

    def _chain_disruption_strategy(
        self,
        priorities: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        coverage_by_technique = {row["technique_id"]: row for row in coverage}
        gap_by_technique = {gap["technique_id"]: gap for gap in gaps}
        strategy: list[dict[str, Any]] = []

        for action in priorities[:5]:
            technique_id = action["technique_id"]
            coverage_row = coverage_by_technique.get(technique_id, {})
            gap = gap_by_technique.get(technique_id, {})
            strategy.append(
                {
                    "technique_id": technique_id,
                    "action": action["title"],
                    "expected_chain_disruption": self._expected_disruption(action),
                    "current_detection_state": {
                        "detected": coverage_row.get("detected", False),
                        "correlated_across_chain": coverage_row.get("correlated_across_chain", False),
                        "response_coverage_effectiveness": coverage_row.get(
                            "response_coverage_effectiveness",
                            "none",
                        ),
                    },
                    "why_now": {
                        "phase": gap.get("phase", "unknown"),
                        "priority_score": gap.get("priority_score"),
                        "attack_chain_severity": gap.get("attack_chain_severity"),
                    },
                    "approval_required": True,
                }
            )
        return strategy

    @staticmethod
    def _expected_disruption(action: dict[str, Any]) -> str:
        action_type = action.get("action_type")
        if action_type == "add_detection_backlog_item":
            return "Increase visibility at a currently undetected chain stage."
        if action_type == "improve_correlation":
            return "Connect isolated detections into a coherent attack chain."
        if action_type == "add_response_playbook":
            return "Improve containment after detection and reduce dwell time."
        return "Reduce telemetry uncertainty for future reasoning."

    def _load_or_build_chains(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "reports" / "attack-chain-analysis.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return [report.to_dict() for report in AttackChainAnalyzer(self.event_bus).analyze()]

    def _load_or_build_coverage(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "reports" / "coverage-matrix.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return [row.to_dict() for row in CoverageMatrix(self.event_bus).build()]

    def _load_or_build_gaps(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "reports" / "prioritized-gaps.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return [gap.to_dict() for gap in GapPrioritizer(self.event_bus).prioritize()]

    def _persist(self, plan: DefensiveActionPlan) -> None:
        path = self.event_bus.repository_root / "reports" / "defense-plan.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    def _emit_event(self, plan: DefensiveActionPlan) -> None:
        top_action = plan.prioritized_actions[0] if plan.prioritized_actions else {}
        event = SocEvent(
            event_type=SocEventType.DEFENSE_PLAN_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/defense-plan.json"},
            normalized_context={
                "action_count": len(plan.prioritized_actions),
                "top_action": top_action.get("action_id", ""),
                "top_technique": top_action.get("technique_id", ""),
            },
        )
        self.event_bus.emit(event)
