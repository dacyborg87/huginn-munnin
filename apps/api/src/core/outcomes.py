"""Outcome data type.

Split out of outcome_tracker.py so core/stores/outcome_store.py can depend
on it without a circular import (outcome_tracker.py in turn depends on the
store implementations). No fields or shapes changed — pure relocation.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


OutcomeResult = Literal["success", "failure", "partial"]


@dataclass(frozen=True)
class Outcome:
    event_id: str
    initial_state: str
    chosen_path: str
    result: OutcomeResult
    execution_time: float
    error_logs: list[str] = field(default_factory=list)
    user_feedback: str | None = None
    performance_score: float = 0.0

    def to_memory(self) -> dict[str, Any]:
        return asdict(self)
