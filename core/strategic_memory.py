"""Long-term defensive intelligence memory for recurring SOC weaknesses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


@dataclass(frozen=True)
class StrategicMemoryPattern:
    pattern_id: str
    pattern_type: str
    key: str
    occurrence_count: int
    related_chains: list[str]
    related_techniques: list[str]
    failure_modes: list[str]
    recommended_focus: str
    status: str = "memory_only"
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "key": self.key,
            "occurrence_count": self.occurrence_count,
            "related_chains": self.related_chains,
            "related_techniques": self.related_techniques,
            "failure_modes": self.failure_modes,
            "recommended_focus": self.recommended_focus,
            "status": self.status,
            "updated_at": self.updated_at,
        }


class StrategicMemory:
    """Identify repeated attack and failure combinations from reports only."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus
        self.memory_path = self.event_bus.repository_root / "core" / "patterns" / "strategic-memory.json"

    def update(self, persist: bool = True) -> list[StrategicMemoryPattern]:
        chains = self._read_report("attack-chain-analysis.json", default=[])
        gaps = self._read_report("prioritized-gaps.json", default=[])
        defense_plan = self._read_report("defense-plan.json", default={})
        attack_success = self._read_report("attack-success-probability.json", default=[])
        patterns = [
            *self._repeated_gap_patterns(chains, gaps),
            *self._attack_failure_combinations(chains, attack_success),
            *self._decision_focus_patterns(defense_plan),
        ]

        if persist:
            self._persist(patterns)
            self._emit_event(patterns)

        return patterns

    def _repeated_gap_patterns(
        self,
        chains: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
    ) -> list[StrategicMemoryPattern]:
        chain_ids = [str(chain.get("chain_id", "unknown")) for chain in chains]
        by_phase: dict[str, dict[str, Any]] = {}
        for gap in gaps:
            phase = str(gap.get("phase", "unknown"))
            bucket = by_phase.setdefault(
                phase,
                {"techniques": set(), "failure_modes": set(), "count": 0},
            )
            bucket["count"] += 1
            bucket["techniques"].add(str(gap.get("technique_id", "")))
            evidence = gap.get("evidence", {})
            if not evidence.get("detected", False):
                bucket["failure_modes"].add("missing_detection")
            if not evidence.get("correlated_across_chain", False):
                bucket["failure_modes"].add("missing_chain_correlation")
            if evidence.get("response_coverage_effectiveness") in {"none", "weak"}:
                bucket["failure_modes"].add("weak_response_coverage")

        patterns: list[StrategicMemoryPattern] = []
        for phase, bucket in sorted(by_phase.items()):
            if not bucket["techniques"]:
                continue
            patterns.append(
                StrategicMemoryPattern(
                    pattern_id=str(uuid4()),
                    pattern_type="recurring_phase_weakness",
                    key=f"phase:{phase}",
                    occurrence_count=int(bucket["count"]),
                    related_chains=chain_ids,
                    related_techniques=sorted(bucket["techniques"]),
                    failure_modes=sorted(bucket["failure_modes"]),
                    recommended_focus=f"Prioritize analyst-reviewed coverage improvements for {phase} activity.",
                )
            )
        return patterns

    def _attack_failure_combinations(
        self,
        chains: list[dict[str, Any]],
        attack_success: list[dict[str, Any]],
    ) -> list[StrategicMemoryPattern]:
        success_by_chain = {str(item.get("chain_id", "")): item for item in attack_success}
        patterns: list[StrategicMemoryPattern] = []
        for chain in chains:
            chain_id = str(chain.get("chain_id", "unknown"))
            estimate = success_by_chain.get(chain_id, {})
            undetected = [str(item) for item in chain.get("undetected_techniques", [])]
            if not undetected:
                continue
            patterns.append(
                StrategicMemoryPattern(
                    pattern_id=str(uuid4()),
                    pattern_type="attack_failure_combination",
                    key=f"{chain_id}:undetected:{','.join(undetected)}",
                    occurrence_count=1,
                    related_chains=[chain_id],
                    related_techniques=undetected,
                    failure_modes=[
                        "telemetry_blind_spot",
                        "missing_transition_visibility",
                    ],
                    recommended_focus=(
                        "Reduce modeled chain success probability through visibility and response coverage "
                        f"for {', '.join(undetected)}."
                    ),
                    status=f"memory_only:risk_score={estimate.get('risk_score', 'unknown')}",
                )
            )
        return patterns

    def _decision_focus_patterns(self, defense_plan: dict[str, Any]) -> list[StrategicMemoryPattern]:
        actions = defense_plan.get("prioritized_actions", [])
        if not actions:
            return []

        top_actions = actions[:3]
        return [
            StrategicMemoryPattern(
                pattern_id=str(uuid4()),
                pattern_type="defensive_decision_focus",
                key="top_defensive_actions",
                occurrence_count=len(top_actions),
                related_chains=[
                    str(item.get("chain_id", "unknown"))
                    for item in defense_plan.get("chain_risk_summary", [])
                ],
                related_techniques=[str(action.get("technique_id", "")) for action in top_actions],
                failure_modes=[str(action.get("action_type", "unknown")) for action in top_actions],
                recommended_focus="Track whether top defensive recommendations reduce future chain risk.",
            )
        ]

    def _read_report(self, filename: str, default: Any) -> Any:
        path = self.event_bus.repository_root / "reports" / filename
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _persist(self, patterns: list[StrategicMemoryPattern]) -> None:
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_path.write_text(
            json.dumps([pattern.to_dict() for pattern in patterns], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_event(self, patterns: list[StrategicMemoryPattern]) -> None:
        event = SocEvent(
            event_type=SocEventType.STRATEGIC_MEMORY_UPDATED,
            source_system=EventSource.MUNINN,
            severity=EventSeverity.INFO,
            raw_payload={"memory_path": "core/patterns/strategic-memory.json"},
            normalized_context={
                "pattern_count": len(patterns),
                "pattern_types": sorted({pattern.pattern_type for pattern in patterns}),
            },
        )
        self.event_bus.emit(event)
