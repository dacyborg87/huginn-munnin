"""Behavioral contract tests for the four storage interfaces.

Each store gets two tests sharing one assertion function: an in-memory test
(always runs, no DB needed) and a Postgres test (self-skips without
TEST_DATABASE_URL). This proves both backends behave identically from the
caller's point of view, which is the whole point of depending on a Protocol
rather than a concrete backend.

Uses asyncio.run() directly rather than pytest-asyncio — no new test-only
dependency needed for a handful of async assertion helpers.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from core.events import Event, EventType
from core.outcomes import Outcome
from core.reasoning_types import Pattern
from core.stores.memory_store import InMemoryMemoryStore, PostgresMemoryStore
from core.stores.outcome_store import InMemoryOutcomeStore, PostgresOutcomeStore
from core.stores.pattern_store import InMemoryPatternStore, PostgresPatternStore
from core.stores.postgres_pool import bootstrap_schema, create_pool
from core.stores.system_log_store import InMemorySystemLogStore, PostgresSystemLogStore
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest


async def _pg_pool(dsn: str):
    pool = await create_pool(dsn)
    await bootstrap_schema(pool)
    return pool


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


async def _assert_memory_store_contract(store) -> None:
    record = MemoryRecord(
        namespace="contract-test",
        content="Investigate T1078 valid account activity",
        tags=["contract", "test"],
        metadata={"note": "contract test"},
    )
    stored = await store.write(record)
    assert stored.id is not None
    assert stored.created_at is not None

    results = await store.search(
        MemorySearchRequest(query="valid account", namespace="contract-test", limit=5)
    )
    assert any(r.id == stored.id for r in results)

    other_namespace = await store.search(
        MemorySearchRequest(query="valid account", namespace="a-different-namespace", limit=5)
    )
    assert all(r.id != stored.id for r in other_namespace)


def test_memory_store_contract_in_memory() -> None:
    asyncio.run(_assert_memory_store_contract(InMemoryMemoryStore()))


@pytest.mark.integration
def test_memory_store_contract_postgres(test_database_url: str) -> None:
    async def run() -> None:
        pool = await _pg_pool(test_database_url)
        try:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM memories WHERE namespace LIKE 'contract-test%'")
            await _assert_memory_store_contract(PostgresMemoryStore(pool))
        finally:
            await pool.close()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# OutcomeStore
# ---------------------------------------------------------------------------


async def _assert_outcome_store_contract(store) -> None:
    outcome = Outcome(
        event_id=str(uuid4()),
        initial_state="THINKING",
        chosen_path="TOOL_USE",
        result="failure",
        execution_time=0.01,
        error_logs=["contract test failure"],
        performance_score=0.0,
    )
    await store.record_outcome(outcome, trace_id=str(uuid4()))

    await store.set_weight("TOOL_USE", -0.2)
    weights = await store.get_weights()
    assert weights["TOOL_USE"] == -0.2

    await store.set_weight("TOOL_USE", -0.3)
    weights = await store.get_weights()
    assert weights["TOOL_USE"] == -0.3

    recent = await store.list_outcomes(limit=10)
    assert any(o.event_id == outcome.event_id for o in recent)


def test_outcome_store_contract_in_memory() -> None:
    asyncio.run(_assert_outcome_store_contract(InMemoryOutcomeStore()))


@pytest.mark.integration
def test_outcome_store_contract_postgres(test_database_url: str) -> None:
    async def run() -> None:
        pool = await _pg_pool(test_database_url)
        try:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM outcomes")
                await conn.execute("DELETE FROM learned_weights WHERE path = 'TOOL_USE'")
            await _assert_outcome_store_contract(PostgresOutcomeStore(pool))
        finally:
            await pool.close()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# SystemLogStore
# ---------------------------------------------------------------------------


async def _assert_system_log_store_contract(store) -> None:
    event = Event(
        event_type=EventType.USER_COMMAND_RECEIVED,
        payload={"message": "contract test", "namespace": "default", "voice_invocation": False},
    )
    await store.write(event)

    logs = await store.list(limit=100)
    matching = [item for item in logs if item.id == event.id]
    assert len(matching) == 1
    reloaded = matching[0]
    assert reloaded.event_type == event.event_type
    assert reloaded.payload == event.payload

    await store.clear()
    assert await store.list(limit=100) == []


def test_system_log_store_contract_in_memory() -> None:
    asyncio.run(_assert_system_log_store_contract(InMemorySystemLogStore()))


@pytest.mark.integration
def test_system_log_store_contract_postgres(test_database_url: str) -> None:
    async def run() -> None:
        pool = await _pg_pool(test_database_url)
        try:
            await _assert_system_log_store_contract(PostgresSystemLogStore(pool))
        finally:
            await pool.close()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# PatternStore
# ---------------------------------------------------------------------------


async def _assert_pattern_store_contract(store, pattern_id_holder: list[str] | None = None) -> None:
    pattern = Pattern(
        pattern_id=str(uuid4()),
        context_signature={"intent": "cybersecurity", "tokens": ["alert", "logs"]},
        preferred_path_distribution={"TOOL_USE": 1.0},
        success_rate=1.0,
        conditions={"intent": "cybersecurity"},
        matched_contexts=1,
        outcomes=[{"chosen_path": "TOOL_USE", "result": "success"}],
    )
    if pattern_id_holder is not None:
        pattern_id_holder.append(pattern.pattern_id)
    await store.save({pattern.pattern_id: pattern})

    loaded = await store.load()
    assert pattern.pattern_id in loaded
    reloaded = loaded[pattern.pattern_id]
    assert reloaded.success_rate == 1.0
    assert reloaded.preferred_path_distribution == {"TOOL_USE": 1.0}
    assert reloaded.outcomes == [{"chosen_path": "TOOL_USE", "result": "success"}]


def test_pattern_store_contract_in_memory() -> None:
    asyncio.run(_assert_pattern_store_contract(InMemoryPatternStore()))


@pytest.mark.integration
def test_pattern_store_contract_postgres(test_database_url: str) -> None:
    async def run() -> None:
        pool = await _pg_pool(test_database_url)
        pattern_id_holder: list[str] = []
        try:
            store = PostgresPatternStore(pool)
            await _assert_pattern_store_contract(store, pattern_id_holder)
        finally:
            # reasoning_patterns is a global table (no namespace column, by
            # design — see schema.sql) shared with every other integration
            # test that reads pattern influence, so this test cleans up the
            # one row it inserted rather than leaving it behind.
            if pattern_id_holder:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM reasoning_patterns WHERE pattern_id = $1",
                        pattern_id_holder[0],
                    )
            await pool.close()

    asyncio.run(run())
