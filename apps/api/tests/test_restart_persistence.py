"""The mandatory restart test.

Process A writes one of each record type via freshly constructed Postgres
stores, then every Process-A object is discarded. Process B constructs
entirely new store objects against the same database — sharing no Python
objects with Process A — and must retrieve everything. This is what proves
persistence rather than accidental object reuse: the property under test is
"no reliance on in-memory state," not literally forking an OS process.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from core.events import Event, EventType
from core.outcomes import Outcome
from core.reasoning_types import ContextSignature, Pattern
from core.stores.memory_store import PostgresMemoryStore
from core.stores.outcome_store import PostgresOutcomeStore
from core.stores.pattern_store import PostgresPatternStore
from core.stores.postgres_pool import bootstrap_schema, create_pool
from core.stores.system_log_store import PostgresSystemLogStore
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest


@pytest.mark.integration
def test_state_survives_independent_process_and_store_creation(test_database_url: str) -> None:
    asyncio.run(_run(test_database_url))


async def _run(dsn: str) -> None:
    trace_id = str(uuid4())
    namespace = f"restart-test-{trace_id}"

    # --- Process A -----------------------------------------------------
    pool_a = await create_pool(dsn)
    await bootstrap_schema(pool_a)

    memory_store_a = PostgresMemoryStore(pool_a)
    outcome_store_a = PostgresOutcomeStore(pool_a)
    log_store_a = PostgresSystemLogStore(pool_a)
    pattern_store_a = PostgresPatternStore(pool_a)

    written_memory = await memory_store_a.write(
        MemoryRecord(
            namespace=namespace,
            content="Restart test: investigate T1078 valid account activity",
            tags=["restart-test"],
            metadata={"command_event_id": trace_id},
        )
    )

    outcome = Outcome(
        event_id=str(uuid4()),
        initial_state="THINKING",
        chosen_path="TOOL_USE",
        result="failure",
        execution_time=0.02,
        error_logs=["restart test simulated failure"],
        performance_score=0.0,
    )
    await outcome_store_a.record_outcome(outcome, trace_id=trace_id)
    await outcome_store_a.set_weight("TOOL_USE", -0.2)

    signature = ContextSignature(
        intent="cybersecurity",
        intent_embedding=[0.1, 0.2, 0.3],
        memory_relevance_summary="none",
        memory_relevance_score=0.0,
        system_state="THINKING",
        tokens=["restart", "test"],
    )
    pattern = Pattern(
        pattern_id=str(uuid4()),
        context_signature=signature.to_dict(),
        preferred_path_distribution={"TOOL_USE": 1.0},
        success_rate=0.0,
        conditions={"intent": "cybersecurity"},
        outcomes=[outcome.to_memory()],
    )
    await pattern_store_a.save({pattern.pattern_id: pattern})

    event = Event(
        event_type=EventType.AI_OUTCOME_RECORDED,
        payload={"command_event_id": trace_id, "selected_path": "TOOL_USE", "result": "failure"},
    )
    await log_store_a.write(event)

    # Dispose of every Process-A object. No reference crosses into Process B.
    await pool_a.close()
    del pool_a, memory_store_a, outcome_store_a, log_store_a, pattern_store_a

    # --- Process B: entirely new store objects, same database ----------
    pool_b = await create_pool(dsn)
    try:
        memory_store_b = PostgresMemoryStore(pool_b)
        outcome_store_b = PostgresOutcomeStore(pool_b)
        log_store_b = PostgresSystemLogStore(pool_b)
        pattern_store_b = PostgresPatternStore(pool_b)

        found_memories = await memory_store_b.search(
            MemorySearchRequest(query="valid account activity", namespace=namespace, limit=5)
        )
        assert any(record.id == written_memory.id for record in found_memories), (
            "memory did not survive independent process/store creation"
        )

        weights = await outcome_store_b.get_weights()
        assert weights["TOOL_USE"] == -0.2, "learned weight did not survive restart"

        outcomes = await outcome_store_b.list_outcomes(limit=50)
        assert any(o.event_id == outcome.event_id for o in outcomes), (
            "outcome did not survive independent process/store creation"
        )

        patterns = await pattern_store_b.load()
        assert pattern.pattern_id in patterns, (
            "reasoning pattern did not survive independent process/store creation"
        )
        assert patterns[pattern.pattern_id].success_rate == 0.0

        logs = await log_store_b.list(limit=200)
        assert any(item.id == event.id for item in logs), (
            "system event did not survive independent process/store creation"
        )
    finally:
        await pool_b.close()
