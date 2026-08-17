"""OutcomeStore Protocol + in-memory and Postgres implementations.

Two responsibilities live here, matching the two things OutcomeTracker
tracks today: the outcome history (append-only, informational) and the
authoritative learned path weights (the "learned_weights" table is the
single source of truth the brief requires — no weight state is
reconstructed from Muninn memory records anymore).
"""

from __future__ import annotations

import json
import uuid
from threading import Lock
from typing import Protocol

import asyncpg

from core.outcomes import Outcome
from core.stores.trace import extract_trace_id


DEFAULT_PATHS = ("PLANNING", "MEMORY_LOOKUP", "TOOL_USE")


class OutcomeStore(Protocol):
    async def record_outcome(self, outcome: Outcome, *, trace_id: str | None = None) -> None: ...

    async def get_weights(self) -> dict[str, float]: ...

    async def set_weight(self, path: str, weight: float) -> None: ...

    async def list_outcomes(self, limit: int = 100) -> list[Outcome]: ...

    async def find_by_trace_id(self, trace_id: str) -> list[Outcome]: ...


class InMemoryOutcomeStore:
    """Today's exact OutcomeTracker storage behavior, moved behind the protocol."""

    def __init__(self) -> None:
        self._outcomes: list[Outcome] = []
        # record_outcome() always accepted a trace_id but never retained it
        # anywhere prior to Phase A2 — this is the one place a store needed
        # a genuine (minimal, symmetric) extension to support trace lookup,
        # since Outcome itself carries no trace_id field to derive it from
        # at read time the way memories/events do.
        self._by_trace: dict[str, list[Outcome]] = {}
        self._weights: dict[str, float] = {path: 0.0 for path in DEFAULT_PATHS}
        self._lock = Lock()

    async def record_outcome(self, outcome: Outcome, *, trace_id: str | None = None) -> None:
        with self._lock:
            self._outcomes.append(outcome)
            if trace_id:
                self._by_trace.setdefault(str(trace_id), []).append(outcome)

    async def get_weights(self) -> dict[str, float]:
        with self._lock:
            return dict(self._weights)

    async def set_weight(self, path: str, weight: float) -> None:
        with self._lock:
            self._weights[path] = weight

    async def list_outcomes(self, limit: int = 100) -> list[Outcome]:
        with self._lock:
            return list(self._outcomes[-limit:])

    async def find_by_trace_id(self, trace_id: str) -> list[Outcome]:
        with self._lock:
            return list(self._by_trace.get(str(trace_id), []))


class PostgresOutcomeStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_outcome(self, outcome: Outcome, *, trace_id: str | None = None) -> None:
        trace_uuid = uuid.UUID(str(trace_id)) if trace_id else None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO outcomes
                    (id, event_id, trace_id, initial_state, chosen_path, result,
                     execution_time, error_logs, user_feedback, performance_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
                """,
                uuid.uuid4(),
                uuid.UUID(outcome.event_id),
                trace_uuid,
                outcome.initial_state,
                outcome.chosen_path,
                outcome.result,
                outcome.execution_time,
                json.dumps(outcome.error_logs),
                outcome.user_feedback,
                outcome.performance_score,
            )

    async def get_weights(self) -> dict[str, float]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT path, weight FROM learned_weights")
        return {row["path"]: row["weight"] for row in rows}

    async def set_weight(self, path: str, weight: float) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO learned_weights (path, weight, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (path) DO UPDATE SET weight = EXCLUDED.weight, updated_at = now()
                """,
                path,
                weight,
            )

    async def list_outcomes(self, limit: int = 100) -> list[Outcome]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, initial_state, chosen_path, result, execution_time,
                       error_logs, user_feedback, performance_score
                FROM (
                    SELECT * FROM outcomes ORDER BY created_at DESC LIMIT $1
                ) recent
                ORDER BY created_at ASC
                """,
                limit,
            )
        return [_row_to_outcome(row) for row in rows]

    async def find_by_trace_id(self, trace_id: str) -> list[Outcome]:
        trace_uuid = extract_trace_id(trace_id)
        if trace_uuid is None:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT event_id, initial_state, chosen_path, result, execution_time,
                       error_logs, user_feedback, performance_score
                FROM outcomes WHERE trace_id = $1 ORDER BY created_at ASC
                """,
                trace_uuid,
            )
        return [_row_to_outcome(row) for row in rows]


def _row_to_outcome(row) -> Outcome:
    return Outcome(
        event_id=str(row["event_id"]),
        initial_state=row["initial_state"],
        chosen_path=row["chosen_path"],
        result=row["result"],
        execution_time=row["execution_time"],
        error_logs=(
            json.loads(row["error_logs"])
            if isinstance(row["error_logs"], str)
            else list(row["error_logs"])
        ),
        user_feedback=row["user_feedback"],
        performance_score=row["performance_score"],
    )
