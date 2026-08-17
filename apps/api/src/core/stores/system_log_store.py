"""SystemLogStore Protocol + in-memory and Postgres implementations.

This is the full event log EventBus writes every dispatched Event to, and
GET /events reads back to feed the dashboard's Decision Graph, Reasoning
Intelligence, and Learning Loop panels. Both backends must reconstruct
Event objects with the exact same externally observable shape — see
apps/api/tests/test_event_store_shape_parity.py for the regression test
that pins this down.
"""

from __future__ import annotations

import json
import uuid
from threading import Lock
from typing import Protocol

import asyncpg

from core.events import Event, EventType
from core.stores.trace import trace_id_from_event_payload


class SystemLogStore(Protocol):
    async def write(self, event: Event) -> None: ...

    async def list(self, limit: int = 100) -> list[Event]: ...

    async def clear(self) -> None: ...


class InMemorySystemLogStore:
    """Today's exact SystemLogStore behavior, moved behind the protocol."""

    def __init__(self) -> None:
        self._logs: list[Event] = []
        self._lock = Lock()

    async def write(self, event: Event) -> None:
        with self._lock:
            self._logs.append(event)

    async def list(self, limit: int = 100) -> list[Event]:
        with self._lock:
            return list(self._logs[-limit:])

    async def clear(self) -> None:
        with self._lock:
            self._logs.clear()


class PostgresSystemLogStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def write(self, event: Event) -> None:
        trace_id = trace_id_from_event_payload(event.payload, event.id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_events (id, event_type, payload, trace_id, created_at)
                VALUES ($1, $2, $3::jsonb, $4, $5)
                ON CONFLICT (id) DO NOTHING
                """,
                uuid.UUID(event.id),
                event.event_type.value,
                json.dumps(event.payload, default=str),
                trace_id,
                event.created_at,
            )

    async def list(self, limit: int = 100) -> list[Event]:
        # InMemorySystemLogStore.list() returns the *most recent* `limit`
        # events in ascending (original append) order via `self._logs[-limit:]`.
        # Match that exactly: take the newest `limit` rows, then re-sort ascending.
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, event_type, payload, created_at FROM (
                    SELECT id, event_type, payload, created_at FROM system_events
                    ORDER BY created_at DESC LIMIT $1
                ) recent
                ORDER BY created_at ASC
                """,
                limit,
            )
        return [
            Event(
                event_type=EventType(row["event_type"]),
                payload=(
                    json.loads(row["payload"])
                    if isinstance(row["payload"], str)
                    else dict(row["payload"])
                ),
                id=str(row["id"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def clear(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM system_events")
