"""Attack surface exposure model from SOC intelligence reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


SURFACE_LAYERS = ("pre-auth", "auth", "post-auth")


@dataclass(frozen=True)
class SurfaceLayerExposure:
    layer: str
    technique_count: int
    detected_count: int
    correlated_count: int
    response_covered_count: int
    instrumentation_score: float
    exposure_level: str
    under_instrumented: bool
    techniques: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "technique_count": self.technique_count,
            "detected_count": self.detected_count,
            "correlated_count": self.correlated_count,
            "response_covered_count": self.response_covered_count,
            "instrumentation_score": self.instrumentation_score,
            "exposure_level": self.exposure_level,
            "under_instrumented": self.under_instrumented,
            "techniques": self.techniques,
        }


class AttackSurfaceModel:
    """Model pre-auth, auth, and post-auth exposure from report artifacts."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus

    def build(self, persist: bool = True) -> list[SurfaceLayerExposure]:
        coverage = self._read_report("coverage-matrix.json", default=[])
        grouped = {layer: [] for layer in SURFACE_LAYERS}
        for row in coverage:
            grouped[self._surface_layer(row)].append(row)

        model = [self._layer_exposure(layer, grouped[layer]) for layer in SURFACE_LAYERS]

        if persist:
            self._persist(model)
            self._emit_event(model)

        return model

    def _layer_exposure(self, layer: str, rows: list[dict[str, Any]]) -> SurfaceLayerExposure:
        technique_count = len(rows)
        detected_count = sum(1 for row in rows if row.get("detected", False))
        correlated_count = sum(1 for row in rows if row.get("correlated_across_chain", False))
        response_covered_count = sum(
            1
            for row in rows
            if row.get("response_coverage_effectiveness") in {"strong", "partial"}
        )
        score = self._instrumentation_score(
            technique_count,
            detected_count,
            correlated_count,
            response_covered_count,
        )
        return SurfaceLayerExposure(
            layer=layer,
            technique_count=technique_count,
            detected_count=detected_count,
            correlated_count=correlated_count,
            response_covered_count=response_covered_count,
            instrumentation_score=score,
            exposure_level=self._exposure_level(score, technique_count),
            under_instrumented=technique_count > 0 and score < 0.6,
            techniques=[
                {
                    "technique_id": row.get("technique_id"),
                    "technique_name": row.get("technique_name"),
                    "detected": row.get("detected"),
                    "correlated_across_chain": row.get("correlated_across_chain"),
                    "response_coverage_effectiveness": row.get("response_coverage_effectiveness"),
                }
                for row in rows
            ],
        )

    def _instrumentation_score(
        self,
        technique_count: int,
        detected_count: int,
        correlated_count: int,
        response_covered_count: int,
    ) -> float:
        if technique_count == 0:
            return 1.0
        detection = detected_count / technique_count
        correlation = correlated_count / technique_count
        response = response_covered_count / technique_count
        return round((detection * 0.45) + (correlation * 0.35) + (response * 0.2), 4)

    def _surface_layer(self, row: dict[str, Any]) -> str:
        technique_id = str(row.get("technique_id", ""))
        tactics = " ".join(str(tactic).lower() for tactic in row.get("tactics", []))
        if technique_id == "T1110" or "credential access" in tactics:
            return "auth"
        if technique_id in {"T1078", "T1087"} or "defense evasion" in tactics:
            return "post-auth"
        return "pre-auth"

    def _exposure_level(self, score: float, technique_count: int) -> str:
        if technique_count == 0:
            return "unknown"
        if score < 0.35:
            return "critical"
        if score < 0.6:
            return "high"
        if score < 0.8:
            return "medium"
        return "low"

    def _read_report(self, filename: str, default: Any) -> Any:
        path = self.event_bus.repository_root / "reports" / filename
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _persist(self, model: list[SurfaceLayerExposure]) -> None:
        path = self.event_bus.repository_root / "reports" / "attack-surface-model.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([layer.to_dict() for layer in model], indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _emit_event(self, model: list[SurfaceLayerExposure]) -> None:
        event = SocEvent(
            event_type=SocEventType.ATTACK_SURFACE_MODEL_CREATED,
            source_system=EventSource.HUGINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/attack-surface-model.json"},
            normalized_context={
                "under_instrumented_layers": [
                    layer.layer for layer in model if layer.under_instrumented
                ],
                "critical_layers": [
                    layer.layer for layer in model if layer.exposure_level == "critical"
                ],
            },
        )
        self.event_bus.emit(event)
