"""Event API shape regression test.

GET /events feeds the dashboard's Decision Graph, Reasoning Intelligence,
and Learning Loop panels — the frontend requires zero changes for this
milestone, which only holds if InMemorySystemLogStore and
PostgresSystemLogStore hand back byte-identical Event objects (same
event_type, same payload contents, same id) for the same input. This test
pins that down directly, independent of the full API/dashboard stack.
"""

from __future__ import annotations

import asyncio

import pytest

from core.events import Event, EventType
from core.stores.postgres_pool import bootstrap_schema, create_pool
from core.stores.system_log_store import InMemorySystemLogStore, PostgresSystemLogStore
from huginn_muninn_api.schemas.events import EventLogEntry


def _sample_event() -> Event:
    return Event(
        event_type=EventType.AI_DECISION_MADE,
        payload={
            "command_event_id": "abc-123",
            "selected_state": "TOOL_USE",
            "confidence_scores": {"TOOL_USE": 0.6, "PLANNING": 0.3, "MEMORY_LOOKUP": 0.1},
            "reasoning": "shape parity test",
            "nested": {"list": [1, 2, 3], "flag": True, "missing": None},
        },
    )


def _to_api_shape(event: Event) -> dict:
    """Exactly what GET /events does in main.py — construct EventLogEntry
    and dump it, so this test pins down what the frontend actually
    receives, not an internal representation."""
    entry = EventLogEntry(
        id=event.id,
        event_type=event.event_type.value,
        payload=event.payload,
        created_at=event.created_at,
    )
    return entry.model_dump(mode="json")


@pytest.mark.integration
def test_inmemory_and_postgres_event_shapes_match(test_database_url: str) -> None:
    asyncio.run(_run(test_database_url))


async def _run(dsn: str) -> None:
    event = _sample_event()

    in_memory_store = InMemorySystemLogStore()
    await in_memory_store.write(event)
    in_memory_result = await in_memory_store.list(limit=10)
    in_memory_shape = _to_api_shape(in_memory_result[0])

    pool = await create_pool(dsn)
    try:
        await bootstrap_schema(pool)
        pg_store = PostgresSystemLogStore(pool)
        await pg_store.write(event)
        pg_result = await pg_store.list(limit=10)
        matching = [item for item in pg_result if item.id == event.id]
        assert len(matching) == 1
        pg_shape = _to_api_shape(matching[0])

        assert pg_shape == in_memory_shape, (
            "Postgres-backed event shape diverged from the in-memory shape "
            "the dashboard has always received — this would break the "
            "Decision Graph / Reasoning Intelligence / Learning Loop panels."
        )
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM system_events WHERE id = $1", event.id)
        await pool.close()
