"""Prioritize attack-chain detection gaps without modifying detections."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.attack_chain_analyzer import PHASE_ORDER, AttackChainAnalyzer, AttackChainReport
from core.coverage_matrix import CoverageMatrix, TechniqueCoverage
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


CHAIN_SEVERITY_SCORE = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

PHASE_EXPLOITABILITY_SCORE = {
    "recon": 1,
    "execution": 3,
    "credential_access": 4,
    "persistence": 4,
    "post-auth": 5,
    "unknown": 2,
}


@dataclass(frozen=True)
class PrioritizedGap:
    rank: int
    technique_id: str
    technique_name: str
    phase: str
    priority_score: float
    severity: str
    attack_chain_severity: str
    exploitability_after_progression: int
    exposure_risk: int
    evidence: dict[str, Any]
    recommendation: str
    status: str = "logged_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "technique_id": self.technique_id,
            "technique_name": self.technique_name,
            "phase": self.phase,
            "priority_score": self.priority_score,
            "severity": self.severity,
            "attack_chain_severity": self.attack_chain_severity,
            "exploitability_after_progression": self.exploitability_after_progression,
            "exposure_risk": self.exposure_risk,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "status": self.status,
        }


class GapPrioritizer:
    """Rank detection gaps from chain analysis and coverage matrix data."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus
        self.pattern_path = self.event_bus.repository_root / "core" / "patterns" / "prioritized-gaps.jsonl"

    def prioritize(self, persist: bool = True) -> list[PrioritizedGap]:
        chain_reports = AttackChainAnalyzer(self.event_bus).analyze(persist=False)
        coverage_rows = CoverageMatrix(self.event_bus).build(persist=False)
        coverage_by_technique = {row.technique_id: row for row in coverage_rows}
        chain_context = self._chain_context_by_technique(chain_reports)

        candidates: list[PrioritizedGap] = []
        for technique_id, row in coverage_by_technique.items():
            if row.detected and row.correlated_across_chain and row.response_coverage_effectiveness in {
                "strong",
                "partial",
            }:
                continue

            context = chain_context.get(
                technique_id,
                {
                    "phase": "unknown",
                    "attack_chain_severity": "low",
                    "missing_transition_count": 0,
                    "appears_after_detected_stage": False,
                },
            )
            phase = str(context["phase"])
            chain_severity = str(context["attack_chain_severity"])
            exploitability = self._exploitability_score(phase, bool(context["appears_after_detected_stage"]))
            exposure = self._exposure_risk(row)
            priority_score = self._priority_score(row, chain_severity, exploitability, exposure)

            candidates.append(
                PrioritizedGap(
                    rank=0,
                    technique_id=technique_id,
                    technique_name=row.technique_name,
                    phase=phase,
                    priority_score=priority_score,
                    severity=self._priority_label(priority_score),
                    attack_chain_severity=chain_severity,
                    exploitability_after_progression=exploitability,
                    exposure_risk=exposure,
                    evidence={
                        "detected": row.detected,
                        "correlated_across_chain": row.correlated_across_chain,
                        "response_coverage_effectiveness": row.response_coverage_effectiveness,
                        "lab_count": row.lab_count,
                        "detection_count": row.detection_count,
                        "playbook_count": row.playbook_count,
                        "missing_transition_count": context["missing_transition_count"],
                    },
                    recommendation=(
                        "Add to detection engineering backlog for analyst review. "
                        "Do not auto-generate or modify detection rules."
                    ),
                )
            )

        ranked = [
            PrioritizedGap(
                rank=index,
                technique_id=gap.technique_id,
                technique_name=gap.technique_name,
                phase=gap.phase,
                priority_score=gap.priority_score,
                severity=gap.severity,
                attack_chain_severity=gap.attack_chain_severity,
                exploitability_after_progression=gap.exploitability_after_progression,
                exposure_risk=gap.exposure_risk,
                evidence=gap.evidence,
                recommendation=gap.recommendation,
                status=gap.status,
            )
            for index, gap in enumerate(
                sorted(candidates, key=lambda candidate: candidate.priority_score, reverse=True),
                start=1,
            )
        ]

        if persist:
            self._persist_priorities(ranked)
            self._emit_priority_event(ranked)

        return ranked

    def _chain_context_by_technique(
        self,
        chain_reports: list[AttackChainReport],
    ) -> dict[str, dict[str, Any]]:
        context: dict[str, dict[str, Any]] = {}
        for report in chain_reports:
            missing_counts: dict[str, int] = {}
            for transition in report.missing_transitions:
                for technique_key in ("from_technique", "to_technique"):
                    technique_id = str(transition.get(technique_key, ""))
                    if technique_id:
                        missing_counts[technique_id] = missing_counts.get(technique_id, 0) + 1

            detected_seen = False
            for step in report.steps:
                current = context.setdefault(
                    step.technique_id,
                    {
                        "phase": step.phase,
                        "attack_chain_severity": report.chain_severity,
                        "missing_transition_count": 0,
                        "appears_after_detected_stage": False,
                    },
                )
                current["phase"] = self._later_phase(str(current["phase"]), step.phase)
                current["attack_chain_severity"] = self._higher_chain_severity(
                    str(current["attack_chain_severity"]),
                    report.chain_severity,
                )
                current["missing_transition_count"] = int(current["missing_transition_count"]) + missing_counts.get(
                    step.technique_id,
                    0,
                )
                current["appears_after_detected_stage"] = bool(
                    current["appears_after_detected_stage"] or (detected_seen and not step.detected)
                )
                detected_seen = detected_seen or step.detected
        return context

    def _priority_score(
        self,
        row: TechniqueCoverage,
        chain_severity: str,
        exploitability: int,
        exposure: int,
    ) -> float:
        detection_gap = 3 if not row.detected else 0
        correlation_gap = 2 if row.detected and not row.correlated_across_chain else 0
        response_gap = 2 if row.response_coverage_effectiveness in {"none", "weak"} else 0
        chain_score = CHAIN_SEVERITY_SCORE.get(chain_severity, 1)
        return round(detection_gap + correlation_gap + response_gap + chain_score + exploitability + exposure, 2)

    @staticmethod
    def _exploitability_score(phase: str, appears_after_detected_stage: bool) -> int:
        score = PHASE_EXPLOITABILITY_SCORE.get(phase, 2)
        if appears_after_detected_stage:
            score += 2
        return score

    @staticmethod
    def _exposure_risk(row: TechniqueCoverage) -> int:
        risk = min(row.lab_count, 5)
        if row.detected and row.detection_count < row.lab_count:
            risk += 1
        if row.response_coverage_effectiveness == "none":
            risk += 2
        return risk

    @staticmethod
    def _priority_label(score: float) -> str:
        if score >= 13:
            return "critical"
        if score >= 10:
            return "high"
        if score >= 7:
            return "medium"
        return "low"

    @staticmethod
    def _later_phase(left: str, right: str) -> str:
        return right if PHASE_ORDER.get(right, 99) > PHASE_ORDER.get(left, 99) else left

    @staticmethod
    def _higher_chain_severity(left: str, right: str) -> str:
        return right if CHAIN_SEVERITY_SCORE.get(right, 1) > CHAIN_SEVERITY_SCORE.get(left, 1) else left

    def _persist_priorities(self, gaps: list[PrioritizedGap]) -> None:
        report_path = self.event_bus.repository_root / "reports" / "prioritized-gaps.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps([gap.to_dict() for gap in gaps], indent=2, sort_keys=True),
            encoding="utf-8",
        )

        self.pattern_path.parent.mkdir(parents=True, exist_ok=True)
        with self.pattern_path.open("a", encoding="utf-8") as destination:
            for gap in gaps:
                destination.write(json.dumps(gap.to_dict(), sort_keys=True) + "\n")

    def _emit_priority_event(self, gaps: list[PrioritizedGap]) -> None:
        event = SocEvent(
            event_type=SocEventType.PRIORITIZED_GAPS_CREATED,
            source_system=EventSource.MUNINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/prioritized-gaps.json"},
            normalized_context={
                "gap_count": len(gaps),
                "top_gap": gaps[0].technique_id if gaps else "",
                "top_gap_severity": gaps[0].severity if gaps else "",
            },
        )
        self.event_bus.emit(event)
