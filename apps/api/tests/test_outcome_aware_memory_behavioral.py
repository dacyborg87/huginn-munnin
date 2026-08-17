"""Phase A1 behavioral test.

Proves through the real memory search path — real MemoryRecord writes and
real store.search() calls, no direct manipulation of the ranking function —
that outcome-aware ranking changes what a search actually returns. Also
proves legacy/unstructured memories and the plain (no-outcome-data) search
path keep working exactly as before.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from core.stores.memory_store import InMemoryMemoryStore, PostgresMemoryStore
from core.stores.postgres_pool import bootstrap_schema, create_pool
from huginn_muninn_api.muninn.memory import MuninnMemory
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest


def _memory(content: str, namespace: str, *, performance_score: float | None = None) -> MemoryRecord:
    metadata = {"outcome": {"performance_score": performance_score}} if performance_score is not None else {}
    return MemoryRecord(namespace=namespace, content=content, tags=[], metadata=metadata)


async def _assert_higher_quality_memory_returned_first(store) -> None:
    namespace = f"behavioral-{uuid.uuid4()}"
    muninn = MuninnMemory(store)

    low_quality = await muninn.write(
        _memory(
            "wazuh alert repeated failed password attempts detected",
            namespace,
            performance_score=0.0,
        )
    )
    high_quality = await muninn.write(
        _memory(
            "wazuh alert repeated failed password attempts confirmed",
            namespace,
            performance_score=1.0,
        )
    )

    results = await muninn.search(
        MemorySearchRequest(
            query="wazuh alert repeated failed password attempts",
            namespace=namespace,
            limit=1,
        )
    )

    assert len(results) == 1
    assert results[0].id == high_quality.id, (
        "the higher-quality (successful) memory must be returned ahead of the "
        "equally-relevant lower-quality (failed) one through the real search path"
    )
    assert low_quality.id  # documented as the one that must NOT be returned


async def _assert_legacy_unstructured_memory_still_searchable(store) -> None:
    """A memory written before outcome-aware ranking existed (or via any
    caller that never supplies metadata) must remain fully searchable —
    Phase A1 must not regress plain, metadata-free memory."""
    namespace = f"legacy-{uuid.uuid4()}"
    muninn = MuninnMemory(store)

    legacy = await muninn.write(
        MemoryRecord(
            namespace=namespace,
            content="legacy memory with no metadata at all",
            tags=[],
            metadata={},
        )
    )

    results = await muninn.search(
        MemorySearchRequest(query="legacy memory metadata", namespace=namespace, limit=5)
    )

    assert len(results) == 1
    assert results[0].id == legacy.id


async def _assert_existing_search_api_behavior_unchanged_for_no_match(store) -> None:
    namespace = f"no-match-{uuid.uuid4()}"
    muninn = MuninnMemory(store)
    await muninn.write(_memory("completely unrelated content about gardening", namespace))

    results = await muninn.search(
        MemorySearchRequest(query="wazuh alert credential access", namespace=namespace, limit=5)
    )

    assert results == []


def test_in_memory_outcome_aware_ranking_behavioral() -> None:
    async def run() -> None:
        store = InMemoryMemoryStore()
        await _assert_higher_quality_memory_returned_first(store)
        await _assert_legacy_unstructured_memory_still_searchable(store)
        await _assert_existing_search_api_behavior_unchanged_for_no_match(store)

    asyncio.run(run())


@pytest.mark.integration
def test_postgres_outcome_aware_ranking_behavioral(test_database_url: str) -> None:
    async def run() -> None:
        pool = await create_pool(test_database_url)
        await bootstrap_schema(pool)
        store = PostgresMemoryStore(pool)
        try:
            await _assert_higher_quality_memory_returned_first(store)
            await _assert_legacy_unstructured_memory_still_searchable(store)
            await _assert_existing_search_api_behavior_unchanged_for_no_match(store)
        finally:
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM memories WHERE namespace LIKE 'behavioral-%' "
                    "OR namespace LIKE 'legacy-%' OR namespace LIKE 'no-match-%'"
                )
            await pool.close()

    asyncio.run(run())
