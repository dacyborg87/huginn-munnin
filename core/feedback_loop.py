"""Outcome feedback capture for SOC detections and response routing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class DetectionOutcome:
    source_event_id: str
    detection_name: str
    selected_playbook: str
    outcome: str
    analyst_notes: str = ""
    suggested_rule_tuning: list[str] = field(default_factory=list)
    outcome_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "source_event_id": self.source_event_id,
            "detection_name": self.detection_name,
            "selected_playbook": self.selected_playbook,
            "outcome": self.outcome,
            "analyst_notes": self.analyst_notes,
            "suggested_rule_tuning": self.suggested_rule_tuning,
            "timestamp": self.timestamp,
        }


class FeedbackLoop:
    """Persist outcomes and pattern suggestions without changing detections."""

    def __init__(self, repository_root: Path | str = ".") -> None:
        self.repository_root = Path(repository_root)
        self.outcome_path = self.repository_root / "reports" / "detection-outcomes.jsonl"
        self.pattern_suggestion_path = self.repository_root / "core" / "patterns" / "suggestions.jsonl"

    def record_outcome(self, outcome: DetectionOutcome) -> str:
        self._append_jsonl(self.outcome_path, outcome.to_dict())

        suggestion = {
            "source": "feedback_loop",
            "source_event_id": outcome.source_event_id,
            "detection_name": outcome.detection_name,
            "outcome": outcome.outcome,
            "suggestions": outcome.suggested_rule_tuning,
            "timestamp": outcome.timestamp,
            "status": "logged_only",
        }
        self._append_jsonl(self.pattern_suggestion_path, suggestion)
        return outcome.outcome_id

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as destination:
            destination.write(json.dumps(record, sort_keys=True) + "\n")
