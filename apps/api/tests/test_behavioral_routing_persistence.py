"""The mandatory behavioral-routing persistence test.

This is the test that proves the milestone's actual purpose: persisted
learning changes future reasoning, not just "a row exists in a table."

Process A runs a real command through the real Orchestrator/EventBus/event
pipeline (the same code path `/chat` uses), forces a failure on the
TOOL_USE branch, and lets the real OutcomeTracker.record() write the
resulting negative weight through to Postgres. Process A is then fully
disposed. Process B constructs an entirely new Orchestrator/EventBus wired
to fresh Postgres stores against the same database, hydrates from it (the
same startup step main.py's lifespan performs), and issues the identical
command. Routing must differ solely because the persisted weight changed —
nothing is inserted into the database directly; the whole learning path is
exercised for real on both sides.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from core.event_bus import EventBus
from core.events import EventType
from core.stores.memory_store import PostgresMemoryStore
from core.stores.outcome_store import PostgresOutcomeStore
from core.stores.pattern_store import PostgresPatternStore
from core.stores.postgres_pool import bootstrap_schema, create_pool
from core.stores.system_log_store import PostgresSystemLogStore
from huginn_muninn_api.core.orchestrator import Orchestrator
from huginn_muninn_api.schemas.chat import ChatRequest

# "logs" -> security_terms -> intent=cybersecurity -> TOOL_USE boosted.
# "simulate failure" -> Orchestrator._determine_outcome() forces result="failure"
# on the TOOL_USE branch (this is the same trigger phrase test_api.py's
# in-memory equivalent test uses; the real outcome-determination logic is
# unmodified, so the same phrase works against the Postgres-backed run).
MESSAGE = "simulate failure analyze logs"


async def _build_orchestrator(pool) -> tuple[Orchestrator, EventBus]:
    event_bus = EventBus(log_store=PostgresSystemLogStore(pool))
    orchestrator = Orchestrator(event_bus)
    orchestrator.muninn.bind_store(PostgresMemoryStore(pool))
    orchestrator.outcome_tracker.bind_store(PostgresOutcomeStore(pool))
    orchestrator.reasoning_patterns.bind_store(PostgresPatternStore(pool))
    await orchestrator.hydrate()
    await event_bus.start()
    return orchestrator, event_bus


@pytest.mark.integration
def test_failure_driven_weight_persists_and_changes_future_routing(test_database_url: str) -> None:
    asyncio.run(_run(test_database_url))


async def _run(dsn: str) -> None:
    # Different namespaces for A and B: isolates Muninn's namespace-scoped
    # memory search so the only thing that can carry over into Process B's
    # decision is the (namespace-independent) learned_weight this test is
    # actually about, not incidental memory-lookup overlap.
    namespace_a = f"routing-test-a-{uuid4()}"
    namespace_b = f"routing-test-b-{uuid4()}"

    # --- Process A -------------------------------------------------------
    pool_a = await create_pool(dsn)
    await bootstrap_schema(pool_a)
    async with pool_a.acquire() as conn:
        # learned_weights and reasoning_patterns are both global tables (no
        # namespace column, by design) shared across every run of this test
        # against the same persistent database. Process B's own request
        # below also records an outcome (it routes somewhere and that
        # branch "succeeds"), which nudges that path's weight — so a full
        # reset here, not just TOOL_USE, is required for the test to be
        # deterministic across repeated runs, not just its first run.
        await conn.execute("DELETE FROM learned_weights")
        await conn.execute("DELETE FROM reasoning_patterns")

    orchestrator_a, event_bus_a = await _build_orchestrator(pool_a)

    baseline_weight = orchestrator_a.outcome_tracker.weights()["TOOL_USE"]
    assert baseline_weight == 0.0, "expected a clean TOOL_USE weight baseline for this test"

    first = await orchestrator_a.chat(ChatRequest(message=MESSAGE, namespace=namespace_a))
    await event_bus_a.drain()

    logs_a = await event_bus_a.list_logs(limit=200)
    decision_a = _find(logs_a, EventType.AI_DECISION_MADE, first.event_id)
    outcome_a = _find(logs_a, EventType.AI_OUTCOME_RECORDED, first.event_id)

    assert decision_a.payload["selected_state"] == "TOOL_USE", (
        "test setup assumption failed: first command must route to TOOL_USE"
    )
    assert outcome_a.payload["result"] == "failure", (
        "test setup assumption failed: 'simulate failure' must force a failure outcome"
    )
    assert outcome_a.payload["updated_weights"]["TOOL_USE"] < 0, (
        "failure did not produce a negative learned weight"
    )

    persisted_weight = orchestrator_a.outcome_tracker.weights()["TOOL_USE"]
    assert persisted_weight < 0

    # Dispose of every Process-A object.
    await event_bus_a.stop()
    await pool_a.close()
    del pool_a, orchestrator_a, event_bus_a

    # --- Process B: entirely new Orchestrator/EventBus, same database ---
    pool_b = await create_pool(dsn)
    try:
        orchestrator_b, event_bus_b = await _build_orchestrator(pool_b)

        # This is the proof point: a brand new process, having only just
        # hydrated from Postgres, already carries the negative weight
        # Process A produced — before it has handled a single request.
        assert orchestrator_b.outcome_tracker.weights()["TOOL_USE"] == persisted_weight, (
            "learned weight was not loaded from Postgres on startup"
        )

        second = await orchestrator_b.chat(ChatRequest(message=MESSAGE, namespace=namespace_b))
        await event_bus_b.drain()

        logs_b = await event_bus_b.list_logs(limit=200)
        decision_b = _find(logs_b, EventType.AI_DECISION_MADE, second.event_id)

        assert decision_b.payload["selected_state"] != "TOOL_USE", (
            "routing was unaffected by the persisted learned weight after restart"
        )
        assert decision_b.payload["learned_weights"]["TOOL_USE"] < 0, (
            "decision context did not carry the persisted weight through to scoring"
        )

        await event_bus_b.stop()
    finally:
        await pool_b.close()


def _find(logs, event_type: EventType, command_event_id: str):
    for entry in logs:
        if entry.event_type == event_type and entry.payload.get("command_event_id") == command_event_id:
            return entry
    raise AssertionError(f"no {event_type} event found for command {command_event_id}")
