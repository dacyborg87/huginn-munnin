"""Track defensive posture improvement over time from SOC reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource, SocEvent, SocEventType


@dataclass(frozen=True)
class EvolutionSnapshot:
    snapshot_id: str
    timestamp: str
    detection_coverage_ratio: float | None
    highest_attack_success_probability: float | None
    open_gap_count: int
    critical_gap_count: int
    gap_closure_rate: float | None
    deltas: dict[str, Any]
    status: str = "measurement_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "detection_coverage_ratio": self.detection_coverage_ratio,
            "highest_attack_success_probability": self.highest_attack_success_probability,
            "open_gap_count": self.open_gap_count,
            "critical_gap_count": self.critical_gap_count,
            "gap_closure_rate": self.gap_closure_rate,
            "deltas": self.deltas,
            "status": self.status,
        }


class DefenseEvolutionTracker:
    """Measure defensive learning progress without applying system changes."""

    def __init__(self, event_bus: SocEventBus) -> None:
        self.event_bus = event_bus
        self.history_path = self.event_bus.repository_root / "reports" / "defense-evolution-history.jsonl"

    def track(self, persist: bool = True) -> EvolutionSnapshot:
        coverage = self._read_report("coverage-matrix.json", default=[])
        attack_success = self._read_report("attack-success-probability.json", default=[])
        gaps = self._read_report("prioritized-gaps.json", default=[])
        previous = self._load_previous_snapshot()
        snapshot = self._build_snapshot(coverage, attack_success, gaps, previous)

        if persist:
            self._persist(snapshot)
            self._emit_event(snapshot)

        return snapshot

    def _build_snapshot(
        self,
        coverage: list[dict[str, Any]],
        attack_success: list[dict[str, Any]],
        gaps: list[dict[str, Any]],
        previous: dict[str, Any] | None,
    ) -> EvolutionSnapshot:
        coverage_ratio = self._coverage_ratio(coverage)
        highest_probability = max(
            (float(item.get("probability", 0)) for item in attack_success),
            default=None,
        )
        open_gap_count = len(gaps)
        critical_gap_count = sum(1 for gap in gaps if gap.get("severity") == "critical")
        previous_gap_count = int(previous.get("open_gap_count", open_gap_count)) if previous else open_gap_count
        gap_closure_rate = self._gap_closure_rate(previous_gap_count, open_gap_count)

        return EvolutionSnapshot(
            snapshot_id=str(uuid4()),
            timestamp=datetime.now(UTC).isoformat(),
            detection_coverage_ratio=coverage_ratio,
            highest_attack_success_probability=highest_probability,
            open_gap_count=open_gap_count,
            critical_gap_count=critical_gap_count,
            gap_closure_rate=gap_closure_rate,
            deltas=self._deltas(previous, coverage_ratio, highest_probability, open_gap_count),
        )

    def _coverage_ratio(self, coverage: list[dict[str, Any]]) -> float | None:
        if not coverage:
            return None
        detected = sum(1 for row in coverage if row.get("detected", False))
        return round(detected / len(coverage), 4)

    def _gap_closure_rate(self, previous_gap_count: int, open_gap_count: int) -> float | None:
        if previous_gap_count <= 0:
            return None
        closed = max(previous_gap_count - open_gap_count, 0)
        return round(closed / previous_gap_count, 4)

    def _deltas(
        self,
        previous: dict[str, Any] | None,
        coverage_ratio: float | None,
        highest_probability: float | None,
        open_gap_count: int,
    ) -> dict[str, Any]:
        if not previous:
            return {
                "coverage_ratio_delta": None,
                "attack_success_probability_delta": None,
                "open_gap_count_delta": None,
                "baseline": True,
            }

        previous_coverage = previous.get("detection_coverage_ratio")
        previous_probability = previous.get("highest_attack_success_probability")
        previous_gap_count = previous.get("open_gap_count")

        return {
            "coverage_ratio_delta": self._delta(coverage_ratio, previous_coverage),
            "attack_success_probability_delta": self._delta(highest_probability, previous_probability),
            "open_gap_count_delta": open_gap_count - int(previous_gap_count)
            if previous_gap_count is not None
            else None,
            "baseline": False,
        }

    def _read_report(self, filename: str, default: Any) -> Any:
        path = self.event_bus.repository_root / "reports" / filename
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_previous_snapshot(self) -> dict[str, Any] | None:
        if not self.history_path.exists():
            return None
        lines = [line for line in self.history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])

    def _persist(self, snapshot: EvolutionSnapshot) -> None:
        current_path = self.event_bus.repository_root / "reports" / "defense-evolution-metrics.json"
        current_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

        with self.history_path.open("a", encoding="utf-8") as destination:
            destination.write(json.dumps(snapshot.to_dict(), sort_keys=True) + "\n")

    def _emit_event(self, snapshot: EvolutionSnapshot) -> None:
        event = SocEvent(
            event_type=SocEventType.DEFENSE_EVOLUTION_METRICS_CREATED,
            source_system=EventSource.MUNINN,
            severity=EventSeverity.INFO,
            raw_payload={"report_path": "reports/defense-evolution-metrics.json"},
            normalized_context={
                "detection_coverage_ratio": snapshot.detection_coverage_ratio,
                "highest_attack_success_probability": snapshot.highest_attack_success_probability,
                "open_gap_count": snapshot.open_gap_count,
                "gap_closure_rate": snapshot.gap_closure_rate,
            },
        )
        self.event_bus.emit(event)

    @staticmethod
    def _delta(current: float | None, previous: Any) -> float | None:
        if current is None or previous is None:
            return None
        return round(current - float(previous), 4)
