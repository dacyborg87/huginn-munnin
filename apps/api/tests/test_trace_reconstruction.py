"""Phase A2 — trace reconstruction.

Covers the store-level `find_by_trace_id()` extensions and the standalone
`reconstruct_trace()` reader, both backends, plus a restart scenario
mirroring the persistence-milestone pattern (fresh stores, same database,
no shared Python objects).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import pytest

# A handful of pre-existing test files collected before this one
# (test_knowledge_graph.py and others) replace sys.modules["core"] with a
# synthetic module pointing only at the repo-root Security Knowledge Graph
# package, for their own isolated imports of that separate `core.*` tree,
# and never restore it. core.trace_reader/core.trace_context are new
# modules nothing else imports early enough to be cached before that swap
# can happen, so force a clean re-resolution rooted at apps/api/src here —
# self-contained to this file, no existing test file is modified.
_API_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _API_SRC in sys.path:
    sys.path.remove(_API_SRC)
sys.path.insert(0, _API_SRC)
sys.modules.pop("core", None)

from core.events import Event, EventType  # noqa: E402
from core.outcomes import Outcome  # noqa: E402
from core.reasoning_types import ContextSignature, Pattern  # noqa: E402
from core.stores.memory_store import InMemoryMemoryStore, PostgresMemoryStore  # noqa: E402
from core.stores.outcome_store import InMemoryOutcomeStore, PostgresOutcomeStore  # noqa: E402
from core.stores.pattern_store import InMemoryPatternStore  # noqa: E402
from core.stores.postgres_pool import bootstrap_schema, create_pool  # noqa: E402
from core.stores.system_log_store import InMemorySystemLogStore, PostgresSystemLogStore  # noqa: E402
from core.trace_reader import reconstruct_trace  # noqa: E402
from huginn_muninn_api.schemas.memory import MemoryRecord  # noqa: E402


def _event(trace_id: str) -> Event:
    return Event(
        event_type=EventType.AI_DECISION_MADE,
        payload={"command_event_id": trace_id, "selected_state": "TOOL_USE"},
    )


def _outcome(event_id: str | None = None) -> Outcome:
    return Outcome(
        event_id=event_id or str(uuid4()),
        initial_state="THINKING",
        chosen_path="TOOL_USE",
        result="success",
        execution_time=0.01,
        performance_score=1.0,
    )


def _memory(trace_id: str | None, content: str = "trace test memory") -> MemoryRecord:
    metadata = {"command_event_id": trace_id} if trace_id else {}
    return MemoryRecord(namespace="trace-test", content=content, tags=[], metadata=metadata)


# ---------------------------------------------------------------------------
# 1. Full trace, in-memory
# ---------------------------------------------------------------------------


def test_full_trace_reconstructs_in_memory() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        written_memory = await memory_store.write(_memory(trace_id))
        outcome = _outcome()
        await outcome_store.record_outcome(outcome, trace_id=trace_id)
        event = _event(trace_id)
        await log_store.write(event)

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )

        assert trace.trace_id == trace_id
        assert [m.id for m in trace.memories] == [written_memory.id]
        assert [o.event_id for o in trace.outcomes] == [outcome.event_id]
        assert [e.id for e in trace.events] == [event.id]
        assert trace.related_patterns == []  # no pattern_store passed
        assert "TOOL_USE" in trace.current_learned_weights

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 2. Partial trace: missing components don't fail
# ---------------------------------------------------------------------------


def test_partial_trace_missing_outcome_and_event_does_not_fail() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        await memory_store.write(_memory(trace_id))
        # No outcome, no event written for this trace_id.

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )

        assert len(trace.memories) == 1
        assert trace.outcomes == []
        assert trace.events == []

    asyncio.run(run())


def test_partial_trace_only_event_does_not_fail() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        await log_store.write(_event(trace_id))

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )

        assert len(trace.events) == 1
        assert trace.memories == []
        assert trace.outcomes == []

    asyncio.run(run())


def test_partial_trace_only_outcome_does_not_fail() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        await outcome_store.record_outcome(_outcome(), trace_id=trace_id)

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )

        assert len(trace.outcomes) == 1
        assert trace.memories == []
        assert trace.events == []

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 3. Unknown trace_id: empty TraceContext, no error
# ---------------------------------------------------------------------------


def test_unknown_trace_id_returns_empty_trace_context() -> None:
    async def run() -> None:
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()
        await memory_store.write(_memory(str(uuid4())))  # unrelated data present

        trace = await reconstruct_trace(
            str(uuid4()),  # never written
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )

        assert trace.memories == []
        assert trace.events == []
        assert trace.outcomes == []
        assert trace.related_patterns == []

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 4. Multiple memories / events all returned
# ---------------------------------------------------------------------------


def test_multiple_memories_and_events_all_returned() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        await memory_store.write(_memory(trace_id, "first memory"))
        await memory_store.write(_memory(trace_id, "second memory"))
        await log_store.write(_event(trace_id))
        await log_store.write(_event(trace_id))

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )

        assert len(trace.memories) == 2
        assert len(trace.events) == 2

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 5. Memory without command_event_id: reconstruction still succeeds
# ---------------------------------------------------------------------------


def test_memory_without_command_event_id_does_not_break_reconstruction() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        # Untraceable write (e.g. via POST /memory directly) — no
        # command_event_id, so trace_id is derived as None and it must
        # never appear in, or break, any trace lookup.
        await memory_store.write(_memory(None, "externally authored memory"))
        await log_store.write(_event(trace_id))

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )

        assert trace.memories == []
        assert len(trace.events) == 1

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 6. Current learned weights: current state, not fabricated history
# ---------------------------------------------------------------------------


def test_current_learned_weights_reflects_live_state_not_trace_time() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        await outcome_store.set_weight("TOOL_USE", -0.2)
        trace_at_first_read = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )
        assert trace_at_first_read.current_learned_weights["TOOL_USE"] == -0.2

        # Weight changes *after* the trace happened — reconstructing the
        # same trace_id again must show the NEW current value, proving this
        # is a live read, not a captured historical snapshot.
        await outcome_store.set_weight("TOOL_USE", 0.4)
        trace_at_second_read = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
        )
        assert trace_at_second_read.current_learned_weights["TOOL_USE"] == 0.4

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Optional pattern correlation: best-effort, never required
# ---------------------------------------------------------------------------


def test_related_pattern_found_by_event_id_correlation() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()
        pattern_store = InMemoryPatternStore()

        outcome = _outcome()
        await outcome_store.record_outcome(outcome, trace_id=trace_id)

        signature = ContextSignature(
            intent="cybersecurity",
            intent_embedding=[0.1, 0.2, 0.3],
            memory_relevance_summary="none",
            memory_relevance_score=0.0,
            system_state="THINKING",
            tokens=["trace", "test"],
        )
        pattern = Pattern(
            pattern_id=str(uuid4()),
            context_signature=signature.to_dict(),
            preferred_path_distribution={"TOOL_USE": 1.0},
            success_rate=1.0,
            conditions={"intent": "cybersecurity"},
            outcomes=[outcome.to_memory()],
        )
        await pattern_store.save({pattern.pattern_id: pattern})

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
            pattern_store=pattern_store,
        )

        assert [p.pattern_id for p in trace.related_patterns] == [pattern.pattern_id]

    asyncio.run(run())


def test_no_matching_pattern_still_succeeds() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()
        pattern_store = InMemoryPatternStore()

        await outcome_store.record_outcome(_outcome(), trace_id=trace_id)
        # pattern_store has no patterns at all.

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
            pattern_store=pattern_store,
        )

        assert trace.related_patterns == []
        assert len(trace.outcomes) == 1  # reconstruction still fully succeeds

    asyncio.run(run())


def test_pattern_store_omitted_entirely_still_succeeds() -> None:
    async def run() -> None:
        trace_id = str(uuid4())
        memory_store = InMemoryMemoryStore()
        outcome_store = InMemoryOutcomeStore()
        log_store = InMemorySystemLogStore()

        await outcome_store.record_outcome(_outcome(), trace_id=trace_id)

        trace = await reconstruct_trace(
            trace_id,
            memory_store=memory_store,
            outcome_store=outcome_store,
            system_log_store=log_store,
            # pattern_store not passed at all
        )

        assert trace.related_patterns == []
        assert len(trace.outcomes) == 1

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 7/8. Postgres: full trace + restart scenario
# ---------------------------------------------------------------------------


async def _pg_pool(dsn: str):
    pool = await create_pool(dsn)
    await bootstrap_schema(pool)
    return pool


@pytest.mark.integration
def test_full_trace_reconstructs_from_postgres(test_database_url: str) -> None:
    async def run() -> None:
        pool = await _pg_pool(test_database_url)
        try:
            memory_store = PostgresMemoryStore(pool)
            outcome_store = PostgresOutcomeStore(pool)
            log_store = PostgresSystemLogStore(pool)

            trace_id = str(uuid4())
            written_memory = await memory_store.write(_memory(trace_id))
            outcome = _outcome()
            await outcome_store.record_outcome(outcome, trace_id=trace_id)
            event = _event(trace_id)
            await log_store.write(event)

            trace = await reconstruct_trace(
                trace_id,
                memory_store=memory_store,
                outcome_store=outcome_store,
                system_log_store=log_store,
            )

            assert [m.id for m in trace.memories] == [written_memory.id]
            assert [o.event_id for o in trace.outcomes] == [outcome.event_id]
            assert [e.id for e in trace.events] == [event.id]
        finally:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM memories WHERE namespace = 'trace-test'")
            await pool.close()

    asyncio.run(run())


# ---------------------------------------------------------------------------
# 9. Restart scenario: fresh stores, same database, no shared objects
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_trace_reconstructs_after_independent_process_and_store_creation(
    test_database_url: str,
) -> None:
    async def run() -> None:
        trace_id = str(uuid4())

        # --- Process A ---------------------------------------------------
        pool_a = await create_pool(test_database_url)
        await bootstrap_schema(pool_a)
        memory_store_a = PostgresMemoryStore(pool_a)
        outcome_store_a = PostgresOutcomeStore(pool_a)
        log_store_a = PostgresSystemLogStore(pool_a)

        written_memory = await memory_store_a.write(_memory(trace_id))
        outcome = _outcome()
        await outcome_store_a.record_outcome(outcome, trace_id=trace_id)
        event = _event(trace_id)
        await log_store_a.write(event)

        await pool_a.close()
        del pool_a, memory_store_a, outcome_store_a, log_store_a

        # --- Process B: entirely new stores, same database ---------------
        pool_b = await create_pool(test_database_url)
        try:
            trace = await reconstruct_trace(
                trace_id,
                memory_store=PostgresMemoryStore(pool_b),
                outcome_store=PostgresOutcomeStore(pool_b),
                system_log_store=PostgresSystemLogStore(pool_b),
            )

            assert [m.id for m in trace.memories] == [written_memory.id]
            assert [o.event_id for o in trace.outcomes] == [outcome.event_id]
            assert [e.id for e in trace.events] == [event.id]
        finally:
            async with pool_b.acquire() as conn:
                await conn.execute("DELETE FROM memories WHERE namespace = 'trace-test'")
            await pool_b.close()

    asyncio.run(run())
