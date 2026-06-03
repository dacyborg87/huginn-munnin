"""Architecture-level defensive weakness analysis from SOC intelligence outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


@dataclass(frozen=True)
class ArchitectureWeakness:
    weakness_id: str
    weakness_type: str
    affected_layer: str
    severity: str
    title: str
    evidence: dict[str, Any]
    architectural_impact: str
    recommendation_scope: str = "architecture_only"
    status: str = "recommendation_only"
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "weakness_id": self.weakness_id,
            "weakness_type": self.weakness_type,
            "affected_layer": self.affected_layer,
            "severity": self.severity,
            "title": self.title,
            "evidence": self.evidence,
            "architectural_impact": self.architectural_impact,
            "recommendation_scope": self.recommendation_scope,
            "status": self.status,
            "timestamp": self.timestamp,
        }


class SecurityArchitectureAnalyzer:
    """Identify system-level blind spots from event bus and report memory."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def analyze(self, persist: bool = True) -> list[ArchitectureWeakness]:
        coverage = self._read_report("coverage-matrix.json", default=[])
        chains = self._read_report("attack-chain-analysis.json", default=[])
        gaps = self._read_report("prioritized-gaps.json", default=[])
        learning = self._read_report("defense-learning-insights.json", default=[])
        strategic_memory = self._read_memory()

        weaknesses = [
            *self._post_auth_weaknesses(coverage, chains, gaps, strategic_memory),
            *self._correlation_weaknesses(chains, strategic_memory),
            *self._response_architecture_weaknesses(coverage, learning),
        ]

        if persist:
            self._persist(weaknesses)
            self._emit_event(weaknesses)

        return weaknesses

    def _post_auth_weaknesses(
        self,
        coverage: list[dict[str, Any]],
        chains: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        strategic_memory: list[dict[str, Any]],
    ) -> list[ArchitectureWeakness]:
        post_auth_gaps = [gap for gap in gaps if gap.get("phase") == "post-auth"]
        post_auth_rows = [
            row for row in coverage if self._surface_layer(row) == "post-auth" and not row.get("detected", False)
        ]
        memory_hits = [
            pattern for pattern in strategic_memory if pattern.get("key") == "phase:post-auth"
        ]
        if not post_auth_gaps and not post_auth_rows and not memory_hits:
            return []

        return [
            ArchitectureWeakness(
                weakness_id=str(uuid4()),
                weakness_type="post_auth_visibility_gap",
                affected_layer="post-auth",
                severity="critical",
                title="Post-auth activity lacks architectural visibility and response coverage",
                evidence={
                    "undetected_post_auth_techniques": sorted(
                        {
                            str(row.get("technique_id"))
                            for row in post_auth_rows
                            if row.get("technique_id")
                        }
                    ),
                    "post_auth_gap_count": len(post_auth_gaps),
                    "chains_with_post_auth_misses": [
                        chain.get("chain_id")
                        for chain in chains
                        if any(
                            step.get("phase") == "post-auth" and not step.get("detected", False)
                            for step in chain.get("steps", [])
                        )
                    ],
                    "strategic_memory_patterns": [pattern.get("pattern_id") for pattern in memory_hits],
                },
                architectural_impact=(
                    "The system can detect early discovery and brute force activity, but loses visibility "
                    "after credential use, allowing a chain to progress without correlated containment."
                ),
            )
        ]

    def _correlation_weaknesses(
        self,
        chains: list[dict[str, Any]],
        strategic_memory: list[dict[str, Any]],
    ) -> list[ArchitectureWeakness]:
        missing_transitions = [
            transition
            for chain in chains
            for transition in chain.get("missing_transitions", [])
        ]
        memory_failure_modes = {
            mode
            for pattern in strategic_memory
            for mode in pattern.get("failure_modes", [])
        }
        if not missing_transitions and "missing_chain_correlation" not in memory_failure_modes:
            return []

        return [
            ArchitectureWeakness(
                weakness_id=str(uuid4()),
                weakness_type="chain_correlation_gap",
                affected_layer="correlation",
                severity="high",
                title="Attack stages are not consistently linked into a defensive chain model",
                evidence={
                    "missing_transition_count": len(missing_transitions),
                    "missing_transitions": missing_transitions,
                    "strategic_failure_modes": sorted(memory_failure_modes),
                },
                architectural_impact=(
                    "Isolated detections can route playbooks, but incomplete transition visibility limits "
                    "chain-level disruption decisions."
                ),
            )
        ]

    def _response_architecture_weaknesses(
        self,
        coverage: list[dict[str, Any]],
        learning: list[dict[str, Any]],
    ) -> list[ArchitectureWeakness]:
        weak_response_rows = [
            row for row in coverage if row.get("response_coverage_effectiveness") in {"none", "weak"}
        ]
        response_insights = [
            insight for insight in learning if insight.get("insight_type") == "response_coverage_failure"
        ]
        if not weak_response_rows and not response_insights:
            return []

        return [
            ArchitectureWeakness(
                weakness_id=str(uuid4()),
                weakness_type="response_orchestration_gap",
                affected_layer="response",
                severity="medium",
                title="Response orchestration is incomplete for under-instrumented techniques",
                evidence={
                    "weak_response_techniques": [
                        row.get("technique_id") for row in weak_response_rows
                    ],
                    "response_learning_insights": [insight.get("insight_id") for insight in response_insights],
                },
                architectural_impact=(
                    "Even when future telemetry is added, affected stages need response routing and playbook "
                    "coverage to reduce dwell time."
                ),
            )
        ]

    def _surface_layer(self, row: dict[str, Any]) -> str:
        technique_id = str(row.get("technique_id", ""))
        tactics = " ".join(str(tactic).lower() for tactic in row.get("tactics", []))
        if technique_id == "T1110" or "credential access" in tactics:
            return "auth"
        if technique_id in {"T1078", "T1087"} or "defense evasion" in tactics:
            return "post-auth"
        return "pre-auth"

    def _read_report(self, filename: str, default: Any) -> Any:
        path = self.event_bus.repository_root / "reports" / filename
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_memory(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "core" / "patterns" / "strategic-memory.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _persist(self, weaknesses: list[ArchitectureWeakness]) -> None:
        path = self.event_bus.repository_root / "reports" / "security-architecture-weaknesses.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([weakness.to_dict() for weakness in weaknesses], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_event(self, weaknesses: list[ArchitectureWeakness]) -> None:
        event = SocEvent(
            event_type=SocEventType.SECURITY_ARCHITECTURE_ANALYSIS_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/security-architecture-weaknesses.json"},
            normalized_context={
                "weakness_count": len(weaknesses),
                "critical_count": sum(1 for item in weaknesses if item.severity == "critical"),
                "affected_layers": sorted({item.affected_layer for item in weaknesses}),
            },
        )
        self.event_bus.emit(event)
