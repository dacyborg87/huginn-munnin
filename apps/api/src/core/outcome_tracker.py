from threading import Lock
from time import perf_counter

from core.outcomes import Outcome, OutcomeResult
from core.stores.outcome_store import InMemoryOutcomeStore, OutcomeStore


class OutcomeTracker:
    def __init__(self, store: OutcomeStore | None = None) -> None:
        self._store = store or InMemoryOutcomeStore()
        self._weights: dict[str, float] = {
            "PLANNING": 0.0,
            "MEMORY_LOOKUP": 0.0,
            "TOOL_USE": 0.0,
        }
        self._lock = Lock()

    def bind_store(self, store: OutcomeStore) -> None:
        """Swap the backing store (used at startup to switch memory -> postgres)."""
        self._store = store

    def start_timer(self) -> float:
        return perf_counter()

    async def hydrate(self) -> None:
        """Load authoritative weights from the store into the in-process cache.

        Postgres → learned_weights → OutcomeTracker cache → Decision Engine.
        Call once at startup; the cache stays authoritative for the process
        lifetime after that, kept in sync on every record().
        """
        weights = await self._store.get_weights()
        with self._lock:
            for path, weight in weights.items():
                self._weights[path] = self._clamp(weight)

    async def record(
        self,
        *,
        event_id: str,
        initial_state: str,
        chosen_path: str,
        result: OutcomeResult,
        started_at: float,
        error_logs: list[str] | None = None,
        user_feedback: str | None = None,
        trace_id: str | None = None,
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

        await self._store.record_outcome(outcome, trace_id=trace_id)

        with self._lock:
            new_weight = self._clamp(
                self._weights.get(chosen_path, 0.0) + self._weight_delta(result)
            )
            self._weights[chosen_path] = new_weight
            weights_snapshot = dict(self._weights)

        await self._store.set_weight(chosen_path, new_weight)
        return outcome, weights_snapshot

    def weights(self) -> dict[str, float]:
        with self._lock:
            return dict(self._weights)

    def load_weights(self, weights: dict[str, float]) -> None:
        """Directly override the in-process cache (used by tests). Does not
        touch the store — for that, write through record()/hydrate()."""
        with self._lock:
            for path, weight in weights.items():
                self._weights[path] = self._clamp(weight)

    async def outcomes(self, limit: int = 100) -> list[Outcome]:
        return await self._store.list_outcomes(limit)

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
