"""SOC intelligence context builder for Huginn/Muninn reasoning."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SocIntelligenceContext:
    detection_events: list[dict[str, Any]] = field(default_factory=list)
    lab_simulations: list[dict[str, Any]] = field(default_factory=list)
    incident_reports: list[dict[str, str]] = field(default_factory=list)
    outcome_history: list[dict[str, Any]] = field(default_factory=list)
    pattern_suggestions: list[dict[str, Any]] = field(default_factory=list)
    gap_findings: list[dict[str, Any]] = field(default_factory=list)
    learning_insights: list[dict[str, Any]] = field(default_factory=list)
    strategic_memory: list[dict[str, Any]] = field(default_factory=list)
    evolution_metrics: dict[str, Any] = field(default_factory=dict)
    architecture_weaknesses: list[dict[str, Any]] = field(default_factory=list)
    design_recommendations: list[dict[str, Any]] = field(default_factory=list)
    attack_surface_model: list[dict[str, Any]] = field(default_factory=list)
    complexity_insights: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detection_events": self.detection_events,
            "lab_simulations": self.lab_simulations,
            "incident_reports": self.incident_reports,
            "outcome_history": self.outcome_history,
            "pattern_suggestions": self.pattern_suggestions,
            "gap_findings": self.gap_findings,
            "learning_insights": self.learning_insights,
            "strategic_memory": self.strategic_memory,
            "evolution_metrics": self.evolution_metrics,
            "architecture_weaknesses": self.architecture_weaknesses,
            "design_recommendations": self.design_recommendations,
            "attack_surface_model": self.attack_surface_model,
            "complexity_insights": self.complexity_insights,
        }


class SocIntelligenceContextBuilder:
    """Aggregate events, labs, reports, and feedback into reasoning context."""

    def __init__(self, repository_root: Path | str = ".") -> None:
        self.repository_root = Path(repository_root)

    def build(self) -> SocIntelligenceContext:
        events = self._read_jsonl(self.repository_root / "reports" / "soc-events.jsonl")
        outcomes = self._read_jsonl(self.repository_root / "reports" / "detection-outcomes.jsonl")
        suggestions = self._read_jsonl(self.repository_root / "core" / "patterns" / "suggestions.jsonl")
        gap_findings = self._read_jsonl(self.repository_root / "core" / "patterns" / "gap-findings.jsonl")
        learning_insights = self._read_jsonl(
            self.repository_root / "core" / "patterns" / "defense-learning-insights.jsonl"
        )

        detection_events = [
            event for event in events if event.get("event_type") == "detection.alert"
        ]
        lab_simulations = [
            event for event in events if event.get("event_type") == "lab.event"
        ]

        return SocIntelligenceContext(
            detection_events=detection_events,
            lab_simulations=lab_simulations,
            incident_reports=self._read_incident_reports(),
            outcome_history=outcomes,
            pattern_suggestions=suggestions,
            gap_findings=gap_findings,
            learning_insights=learning_insights,
            strategic_memory=self._read_json(
                self.repository_root / "core" / "patterns" / "strategic-memory.json",
                default=[],
            ),
            evolution_metrics=self._read_json(
                self.repository_root / "reports" / "defense-evolution-metrics.json",
                default={},
            ),
            architecture_weaknesses=self._read_json(
                self.repository_root / "reports" / "security-architecture-weaknesses.json",
                default=[],
            ),
            design_recommendations=self._read_json(
                self.repository_root / "reports" / "defense-design-recommendations.json",
                default=[],
            ),
            attack_surface_model=self._read_json(
                self.repository_root / "reports" / "attack-surface-model.json",
                default=[],
            ),
            complexity_insights=self._read_json(
                self.repository_root / "reports" / "defense-complexity-insights.json",
                default=[],
            ),
        )

    def _read_incident_reports(self) -> list[dict[str, str]]:
        reports_dir = self.repository_root / "reports"
        if not reports_dir.exists():
            return []

        reports: list[dict[str, str]] = []
        for path in sorted(reports_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            reports.append({"path": str(path), "content": path.read_text(encoding="utf-8")})
        return reports

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
