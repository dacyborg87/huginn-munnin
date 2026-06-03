"""Estimate attack-chain success probability from SOC intelligence reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.attack_chain_analyzer import AttackChainAnalyzer
from core.coverage_matrix import CoverageMatrix
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


SEVERITY_WEIGHT = {
    "low": 0.15,
    "medium": 0.3,
    "high": 0.45,
    "critical": 0.6,
}

RESPONSE_REDUCTION = {
    "strong": 0.25,
    "partial": 0.1,
    "weak": 0.0,
    "none": 0.0,
}


@dataclass(frozen=True)
class AttackSuccessEstimate:
    chain_id: str
    probability: float
    risk_score: int
    risk_level: str
    detection_gap_factor: float
    response_weakness_factor: float
    telemetry_blind_spot_factor: float
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "probability": self.probability,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "detection_gap_factor": self.detection_gap_factor,
            "response_weakness_factor": self.response_weakness_factor,
            "telemetry_blind_spot_factor": self.telemetry_blind_spot_factor,
            "evidence": self.evidence,
        }


class AttackSuccessModel:
    """Model attack success risk using event-derived reports only."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def estimate(self, persist: bool = True) -> list[AttackSuccessEstimate]:
        chains = self._load_or_build_chains()
        coverage = {row["technique_id"]: row for row in self._load_or_build_coverage()}
        estimates = [self._estimate_chain(chain, coverage) for chain in chains]

        if persist:
            self._persist(estimates)
            self._emit_event(estimates)

        return estimates

    def _estimate_chain(
        self,
        chain: dict[str, Any],
        coverage: dict[str, dict[str, Any]],
    ) -> AttackSuccessEstimate:
        steps = chain.get("steps", [])
        technique_sequence = [str(step.get("technique_id", "")) for step in steps if step.get("technique_id")]
        total_steps = len(technique_sequence)
        undetected = [step for step in steps if step.get("technique_id") and not step.get("detected")]
        detected = [step for step in steps if step.get("technique_id") and step.get("detected")]
        no_response = [
            step for step in steps if step.get("technique_id") and not step.get("response_routed")
        ]

        detection_gap_factor = len(undetected) / total_steps if total_steps else 0.0
        telemetry_blind_spot_factor = self._telemetry_blind_spot_factor(technique_sequence, coverage)
        response_weakness_factor = self._response_weakness_factor(technique_sequence, coverage)
        base = SEVERITY_WEIGHT.get(str(chain.get("chain_severity", "low")), 0.15)

        probability = base + (detection_gap_factor * 0.25) + (response_weakness_factor * 0.2)
        probability += telemetry_blind_spot_factor * 0.15
        probability -= self._response_reduction(technique_sequence, coverage)
        probability = max(0.01, min(0.99, round(probability, 4)))
        risk_score = round(probability * 100)

        return AttackSuccessEstimate(
            chain_id=str(chain.get("chain_id", "unknown")),
            probability=probability,
            risk_score=risk_score,
            risk_level=self._risk_level(risk_score),
            detection_gap_factor=round(detection_gap_factor, 4),
            response_weakness_factor=round(response_weakness_factor, 4),
            telemetry_blind_spot_factor=round(telemetry_blind_spot_factor, 4),
            evidence={
                "chain_severity": chain.get("chain_severity", "low"),
                "total_steps": total_steps,
                "detected_steps": len(detected),
                "undetected_steps": len(undetected),
                "steps_without_response": len(no_response),
                "missing_transitions": len(chain.get("missing_transitions", [])),
                "undetected_techniques": chain.get("undetected_techniques", []),
            },
        )

    def _telemetry_blind_spot_factor(
        self,
        technique_sequence: list[str],
        coverage: dict[str, dict[str, Any]],
    ) -> float:
        if not technique_sequence:
            return 0.0
        blind_spots = [
            technique_id
            for technique_id in technique_sequence
            if not coverage.get(technique_id, {}).get("detected", False)
        ]
        return len(blind_spots) / len(technique_sequence)

    def _response_weakness_factor(
        self,
        technique_sequence: list[str],
        coverage: dict[str, dict[str, Any]],
    ) -> float:
        if not technique_sequence:
            return 0.0
        weak = [
            technique_id
            for technique_id in technique_sequence
            if coverage.get(technique_id, {}).get("response_coverage_effectiveness") in {"none", "weak"}
        ]
        return len(weak) / len(technique_sequence)

    def _response_reduction(
        self,
        technique_sequence: list[str],
        coverage: dict[str, dict[str, Any]],
    ) -> float:
        reductions = [
            RESPONSE_REDUCTION.get(
                str(coverage.get(technique_id, {}).get("response_coverage_effectiveness", "none")),
                0.0,
            )
            for technique_id in technique_sequence
        ]
        return sum(reductions) / len(reductions) if reductions else 0.0

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

    def _persist(self, estimates: list[AttackSuccessEstimate]) -> None:
        path = self.event_bus.repository_root / "reports" / "attack-success-probability.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([estimate.to_dict() for estimate in estimates], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_event(self, estimates: list[AttackSuccessEstimate]) -> None:
        top = max(estimates, key=lambda estimate: estimate.risk_score, default=None)
        event = SocEvent(
            event_type=SocEventType.ATTACK_SUCCESS_MODEL_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/attack-success-probability.json"},
            normalized_context={
                "chain_count": len(estimates),
                "highest_risk_chain": top.chain_id if top else "",
                "highest_risk_score": top.risk_score if top else 0,
            },
        )
        self.event_bus.emit(event)

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 75:
            return "critical"
        if score >= 55:
            return "high"
        if score >= 35:
            return "medium"
        return "low"
