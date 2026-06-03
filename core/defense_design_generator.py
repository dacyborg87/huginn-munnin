"""Generate architecture-level defensive design recommendations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.attack_surface_model import AttackSurfaceModel
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType
from core.security_architecture_analyzer import SecurityArchitectureAnalyzer


@dataclass(frozen=True)
class DefenseDesignRecommendation:
    recommendation_id: str
    design_area: str
    title: str
    recommended_subsystem: str
    architectural_change: str
    expected_outcome: str
    depends_on: list[str]
    guardrails: list[str]
    status: str = "recommendation_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "design_area": self.design_area,
            "title": self.title,
            "recommended_subsystem": self.recommended_subsystem,
            "architectural_change": self.architectural_change,
            "expected_outcome": self.expected_outcome,
            "depends_on": self.depends_on,
            "guardrails": self.guardrails,
            "status": self.status,
        }


class DefenseDesignGenerator:
    """Convert architecture weaknesses into system design recommendations."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def generate(self, persist: bool = True) -> list[DefenseDesignRecommendation]:
        weaknesses = self._load_or_build_weaknesses()
        surface = self._load_or_build_surface_model()
        recommendations = [
            *self._weakness_recommendations(weaknesses),
            *self._surface_recommendations(surface),
        ]
        recommendations = self._dedupe(recommendations)

        if persist:
            self._persist(recommendations)
            self._emit_event(recommendations)

        return recommendations

    def _weakness_recommendations(
        self,
        weaknesses: list[dict[str, Any]],
    ) -> list[DefenseDesignRecommendation]:
        recommendations: list[DefenseDesignRecommendation] = []
        for weakness in weaknesses:
            weakness_type = weakness.get("weakness_type")
            if weakness_type == "post_auth_visibility_gap":
                recommendations.append(
                    DefenseDesignRecommendation(
                        recommendation_id="design.post_auth_telemetry_layer",
                        design_area="telemetry_layer",
                        title="Add a post-auth telemetry enrichment layer",
                        recommended_subsystem="Post-auth activity monitor",
                        architectural_change=(
                            "Introduce a subsystem that normalizes successful logon context, session activity, "
                            "account enumeration, and follow-on host discovery into canonical SOC events."
                        ),
                        expected_outcome=(
                            "Reduce blind spots after credential access and support chain disruption before "
                            "lateral movement."
                        ),
                        depends_on=["canonical event schema", "event bus", "strategic memory"],
                        guardrails=["Do not generate detection rules", "Require analyst-approved telemetry mapping"],
                    )
                )
            elif weakness_type == "chain_correlation_gap":
                recommendations.append(
                    DefenseDesignRecommendation(
                        recommendation_id="design.chain_correlation_service",
                        design_area="correlation_architecture",
                        title="Add an attack-chain correlation service",
                        recommended_subsystem="Chain correlation service",
                        architectural_change=(
                            "Maintain sliding windows of related source, account, host, and MITRE stage context "
                            "so isolated detections become chain-aware decisions."
                        ),
                        expected_outcome="Increase correlation across attack stages and reduce missed transitions.",
                        depends_on=["event bus", "attack chain analyzer", "coverage matrix"],
                        guardrails=["Recommendation-only", "No automatic containment"],
                    )
                )
            elif weakness_type == "response_orchestration_gap":
                recommendations.append(
                    DefenseDesignRecommendation(
                        recommendation_id="design.response_orchestration_index",
                        design_area="response_architecture",
                        title="Create a response coverage index",
                        recommended_subsystem="Response orchestration index",
                        architectural_change=(
                            "Track which MITRE stages have response playbook coverage, expected evidence, "
                            "and escalation criteria."
                        ),
                        expected_outcome="Expose response gaps before new detections are promoted.",
                        depends_on=["playbook routes", "coverage matrix"],
                        guardrails=["Do not auto-create playbooks", "Require SOC review"],
                    )
                )
        return recommendations

    def _surface_recommendations(
        self,
        surface: list[dict[str, Any]],
    ) -> list[DefenseDesignRecommendation]:
        recommendations: list[DefenseDesignRecommendation] = []
        for layer in surface:
            if not layer.get("under_instrumented", False):
                continue
            recommendations.append(
                DefenseDesignRecommendation(
                    recommendation_id=f"design.surface_instrumentation.{layer.get('layer')}",
                    design_area="attack_surface_instrumentation",
                    title=f"Improve {layer.get('layer')} attack surface instrumentation",
                    recommended_subsystem=f"{layer.get('layer')} instrumentation map",
                    architectural_change=(
                        "Define required telemetry, correlation keys, response coverage, and evidence expectations "
                        "for this attack surface layer."
                    ),
                    expected_outcome="Raise instrumentation score and reduce modeled attack success probability.",
                    depends_on=["attack surface model", "coverage matrix"],
                    guardrails=["No detector edits", "No automatic lab changes"],
                )
            )
        return recommendations

    def _load_or_build_weaknesses(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "reports" / "security-architecture-weaknesses.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return [item.to_dict() for item in SecurityArchitectureAnalyzer(self.event_bus).analyze()]

    def _load_or_build_surface_model(self) -> list[dict[str, Any]]:
        path = self.event_bus.repository_root / "reports" / "attack-surface-model.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return [item.to_dict() for item in AttackSurfaceModel(self.event_bus).build()]

    def _dedupe(
        self,
        recommendations: list[DefenseDesignRecommendation],
    ) -> list[DefenseDesignRecommendation]:
        deduped: dict[str, DefenseDesignRecommendation] = {}
        for recommendation in recommendations:
            deduped.setdefault(recommendation.recommendation_id, recommendation)
        return list(deduped.values())

    def _persist(self, recommendations: list[DefenseDesignRecommendation]) -> None:
        path = self.event_bus.repository_root / "reports" / "defense-design-recommendations.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([item.to_dict() for item in recommendations], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_event(self, recommendations: list[DefenseDesignRecommendation]) -> None:
        event = SocEvent(
            event_type=SocEventType.DEFENSE_DESIGN_RECOMMENDATIONS_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/defense-design-recommendations.json"},
            normalized_context={
                "recommendation_count": len(recommendations),
                "design_areas": sorted({item.design_area for item in recommendations}),
            },
        )
        self.event_bus.emit(event)
