from dataclasses import asdict, dataclass, field
from threading import Lock
from time import perf_counter
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


class OutcomeTracker:
    def __init__(self) -> None:
        self._outcomes: list[Outcome] = []
        self._weights: dict[str, float] = {
            "PLANNING": 0.0,
            "MEMORY_LOOKUP": 0.0,
            "TOOL_USE": 0.0,
        }
        self._lock = Lock()

    def start_timer(self) -> float:
        return perf_counter()

    def record(
        self,
        *,
        event_id: str,
        initial_state: str,
        chosen_path: str,
        result: OutcomeResult,
        started_at: float,
        error_logs: list[str] | None = None,
        user_feedback: str | None = None,
    ) -> tuple[Outcome, dict[str, float]]:
        execution_time = round(perf_counter() - started_at, 4)
        performance_score = self._performance_score(result, execution_time)
        outcome = Outcome(
            event_id=event_id,
            initial_state=initial_state,
            chosen_path=chosen_path,
            result=result,
            execution_time=execution_time,
            error_logs=error_logs or [],
            user_feedback=user_feedback,
            performance_score=performance_score,
        )

        with self._lock:
            self._outcomes.append(outcome)
            self._weights[chosen_path] = self._clamp(
                self._weights.get(chosen_path, 0.0) + self._weight_delta(result)
            )
            return outcome, dict(self._weights)

    def weights(self) -> dict[str, float]:
        with self._lock:
            return dict(self._weights)

    def load_weights(self, weights: dict[str, float]) -> None:
        with self._lock:
            for path, weight in weights.items():
                self._weights[path] = self._clamp(weight)

    def outcomes(self) -> list[Outcome]:
        with self._lock:
            return list(self._outcomes)

    def _weight_delta(self, result: OutcomeResult) -> float:
        if result == "success":
            return 0.1
        if result == "failure":
            return -0.2
        return -0.05

    def _performance_score(self, result: OutcomeResult, execution_time: float) -> float:
        base = {"success": 1.0, "partial": 0.55, "failure": 0.0}[result]
        latency_penalty = min(0.2, execution_time / 10)
        return round(max(0.0, base - latency_penalty), 3)

    def _clamp(self, weight: float) -> float:
        return round(max(-0.6, min(0.6, weight)), 3)
