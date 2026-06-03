"""Rank defensive improvements by risk reduction and chain disruption value."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.attack_success_model import AttackSuccessModel
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType
from core.gap_prioritizer import GapPrioritizer


PHASE_DISRUPTION_VALUE = {
    "recon": 2,
    "execution": 4,
    "credential_access": 5,
    "persistence": 5,
    "post-auth": 4,
    "unknown": 2,
}

EFFICIENCY_BY_ACTION = {
    "improve_correlation": 4,
    "add_response_playbook": 4,
    "add_detection_backlog_item": 3,
    "improve_telemetry": 2,
}


@dataclass(frozen=True)
class DefensiveImprovement:
    rank: int
    action_id: str
    action_type: str
    technique_id: str
    title: str
    risk_reduction_impact: float
    chain_disruption_value: int
    implementation_efficiency: int
    priority_score: float
    evidence: dict[str, Any]
    status: str = "recommendation_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "action_id": self.action_id,
            "action_type": self.action_type,
            "technique_id": self.technique_id,
            "title": self.title,
            "risk_reduction_impact": self.risk_reduction_impact,
            "chain_disruption_value": self.chain_disruption_value,
            "implementation_efficiency": self.implementation_efficiency,
            "priority_score": self.priority_score,
            "evidence": self.evidence,
            "status": self.status,
        }


class DefensePrioritizer:
    """Prioritize defensive actions without applying changes."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def prioritize(self, persist: bool = True) -> list[DefensiveImprovement]:
        gaps = self._load_or_build_gaps()
        success_estimates = self._load_or_build_success_estimates()
        max_risk = max((estimate.get("risk_score", 0) for estimate in success_estimates), default=0)
        candidates = [self._candidate_from_gap(gap, max_risk) for gap in gaps]

        ranked = [
            DefensiveImprovement(
                rank=index,
                action_id=action.action_id,
                action_type=action.action_type,
                technique_id=action.technique_id,
                title=action.title,
                risk_reduction_impact=action.risk_reduction_impact,
                chain_disruption_value=action.chain_disruption_value,
                implementation_efficiency=action.implementation_efficiency,
                priority_score=action.priority_score,
                evidence=action.evidence,
                status=action.status,
            )
            for index, action in enumerate(
                sorted(candidates, key=lambda candidate: candidate.priority_score, reverse=True),
                start=1,
            )
        ]

        if persist:
            self._persist(ranked)
            self._emit_event(ranked)

        return ranked

    def _candidate_from_gap(self, gap: dict[str, Any], max_risk: int) -> DefensiveImprovement:
        action_type = self._action_type(gap)
        chain_disruption_value = PHASE_DISRUPTION_VALUE.get(str(gap.get("phase", "unknown")), 2)
        implementation_efficiency = EFFICIENCY_BY_ACTION[action_type]
        risk_reduction = self._risk_reduction(gap, max_risk, chain_disruption_value)
        priority_score = round(risk_reduction + chain_disruption_value + implementation_efficiency, 2)
        technique_id = str(gap.get("technique_id", "unknown"))

        return DefensiveImprovement(
            rank=0,
            action_id=f"defense.{action_type}.{technique_id.lower()}",
            action_type=action_type,
            technique_id=technique_id,
            title=self._title(action_type, gap),
            risk_reduction_impact=risk_reduction,
            chain_disruption_value=chain_disruption_value,
            implementation_efficiency=implementation_efficiency,
            priority_score=priority_score,
            evidence={
                "gap_priority_score": gap.get("priority_score", 0),
                "gap_severity": gap.get("severity", "low"),
                "attack_chain_severity": gap.get("attack_chain_severity", "low"),
                "phase": gap.get("phase", "unknown"),
                "max_attack_success_risk": max_risk,
                "gap_evidence": gap.get("evidence", {}),
            },
        )

    def _action_type(self, gap: dict[str, Any]) -> str:
        evidence = gap.get("evidence", {})
        if not evidence.get("detected", False):
            return "add_detection_backlog_item"
        if not evidence.get("correlated_across_chain", False):
            return "improve_correlation"
        if evidence.get("response_coverage_effectiveness") in {"none", "weak"}:
            return "add_response_playbook"
        return "improve_telemetry"

    def _risk_reduction(self, gap: dict[str, Any], max_risk: int, chain_disruption_value: int) -> float:
        gap_score = float(gap.get("priority_score", 0))
        risk_multiplier = max(max_risk, 1) / 100
        return round((gap_score * 0.45) + (chain_disruption_value * risk_multiplier), 2)

    def _load_or_build_gaps(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "reports" / "prioritized-gaps.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return [gap.to_dict() for gap in GapPrioritizer(self.event_bus).prioritize()]

    def _load_or_build_success_estimates(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "reports" / "attack-success-probability.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return [estimate.to_dict() for estimate in AttackSuccessModel(self.event_bus).estimate()]

    def _persist(self, improvements: list[DefensiveImprovement]) -> None:
        path = self.event_bus.repository_root / "reports" / "defense-priorities.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([improvement.to_dict() for improvement in improvements], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_event(self, improvements: list[DefensiveImprovement]) -> None:
        top = improvements[0] if improvements else None
        event = SocEvent(
            event_type=SocEventType.DEFENSE_PRIORITIES_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/defense-priorities.json"},
            normalized_context={
                "action_count": len(improvements),
                "top_action": top.action_id if top else "",
                "top_priority_score": top.priority_score if top else 0,
            },
        )
        self.event_bus.emit(event)

    @staticmethod
    def _title(action_type: str, gap: dict[str, Any]) -> str:
        technique_id = gap.get("technique_id", "unknown")
        technique_name = gap.get("technique_name", "")
        if action_type == "add_detection_backlog_item":
            return f"Create manually reviewed detection backlog item for {technique_id} {technique_name}".strip()
        if action_type == "improve_correlation":
            return f"Correlate {technique_id} across the observed attack chain"
        if action_type == "add_response_playbook":
            return f"Add response coverage for {technique_id}"
        return f"Improve telemetry coverage for {technique_id}"
