"""Phase A1 — outcome-aware memory ranking.

Tests the shared `_rank_by_overlap()` function directly for precise,
deterministic control over recency/quality/malformed-input cases, plus a
handful of Postgres-backed `search()` tests proving the same behavior
reaches the real backend (the function is shared by both stores, so full
duplication across every case would be redundant — see memory_store.py's
own docstring on why one shared function is enough to guarantee parity).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from core.stores.memory_store import (
    InMemoryMemoryStore,
    PostgresMemoryStore,
    _rank_by_overlap,
)
from core.stores.postgres_pool import bootstrap_schema, create_pool
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest

CONTENT = "investigate suspicious login activity across the network"
QUERY = "suspicious login activity"


def _record(
    content: str = CONTENT,
    *,
    performance_score: float | None = None,
    created_at: datetime | None = None,
    metadata_override: dict | None = None,
    namespace: str = "ranking-test",
) -> MemoryRecord:
    if metadata_override is not None:
        metadata = metadata_override
    elif performance_score is not None:
        metadata = {"outcome": {"performance_score": performance_score}}
    else:
        metadata = {}
    return MemoryRecord(
        id=str(uuid.uuid4()),
        namespace=namespace,
        content=content,
        tags=[],
        metadata=metadata,
        created_at=created_at,
    )


def _request(query: str = QUERY, limit: int = 5, namespace: str = "ranking-test") -> MemorySearchRequest:
    return MemorySearchRequest(query=query, namespace=namespace, limit=limit)


# ---------------------------------------------------------------------------
# 1. Equal overlap: quality decides
# ---------------------------------------------------------------------------


def test_equal_overlap_higher_quality_ranks_first() -> None:
    now = datetime.now(UTC)
    high = _record(performance_score=1.0, created_at=now)
    low = _record(performance_score=0.0, created_at=now)

    ranked = _rank_by_overlap([low, high], _request(limit=1), now=now)

    assert ranked[0].id == high.id


# ---------------------------------------------------------------------------
# 2. Recency: newer wins when quality is equal
# ---------------------------------------------------------------------------


def test_equal_quality_newer_record_ranks_first() -> None:
    now = datetime.now(UTC)
    newer = _record(performance_score=0.5, created_at=now)
    older = _record(performance_score=0.5, created_at=now - timedelta(days=60))

    ranked = _rank_by_overlap([older, newer], _request(limit=1), now=now)

    assert ranked[0].id == newer.id


# ---------------------------------------------------------------------------
# 3. Overlap dominance: quality/recency cannot displace a strong match
# ---------------------------------------------------------------------------


def test_strong_overlap_beats_weak_overlap_despite_quality_and_recency() -> None:
    now = datetime.now(UTC)
    query = "wazuh alert repeated failed password attempts"
    strong = _record(
        "wazuh alert repeated failed password attempts were logged tonight",
        performance_score=0.0,
        created_at=now - timedelta(days=90),
    )
    weak = _record(
        "wazuh sent an alert about the lunch menu today",
        performance_score=1.0,
        created_at=now,
    )

    ranked = _rank_by_overlap([weak, strong], _request(query=query, limit=2), now=now)

    assert ranked[0].id == strong.id, (
        "a strongly relevant but old/failed memory must still outrank a "
        "weakly relevant but new/successful one"
    )


# ---------------------------------------------------------------------------
# 4/5. Missing / malformed outcome metadata: no crash, neutral quality
# ---------------------------------------------------------------------------


def test_missing_outcome_metadata_does_not_crash() -> None:
    now = datetime.now(UTC)
    record = _record(metadata_override={}, created_at=now)

    ranked = _rank_by_overlap([record], _request(), now=now)

    assert ranked == [record]


def test_malformed_outcome_metadata_does_not_crash() -> None:
    now = datetime.now(UTC)
    record = _record(metadata_override={"outcome": "malformed"}, created_at=now)

    ranked = _rank_by_overlap([record], _request(), now=now)

    assert ranked == [record]


def test_metadata_not_a_dict_does_not_crash() -> None:
    now = datetime.now(UTC)
    record = MemoryRecord.model_construct(
        id=str(uuid.uuid4()),
        namespace="ranking-test",
        content=CONTENT,
        tags=[],
        metadata="not-a-dict",  # type: ignore[arg-type]
        created_at=now,
    )

    ranked = _rank_by_overlap([record], _request(), now=now)

    assert ranked == [record]


# ---------------------------------------------------------------------------
# 6. Invalid performance values: non-numeric and out-of-range
# ---------------------------------------------------------------------------


def test_non_numeric_performance_score_does_not_crash() -> None:
    now = datetime.now(UTC)
    record = _record(
        metadata_override={"outcome": {"performance_score": "very good"}}, created_at=now
    )

    ranked = _rank_by_overlap([record], _request(), now=now)

    assert ranked == [record]


def test_nan_performance_score_does_not_crash() -> None:
    now = datetime.now(UTC)
    record = _record(
        metadata_override={"outcome": {"performance_score": float("nan")}}, created_at=now
    )

    ranked = _rank_by_overlap([record], _request(), now=now)

    assert ranked == [record]


def test_out_of_range_performance_score_is_clamped_not_crashed() -> None:
    now = datetime.now(UTC)
    too_high = _record(performance_score=5.0, created_at=now)
    too_low = _record(performance_score=-3.0, created_at=now)

    ranked = _rank_by_overlap([too_low, too_high], _request(limit=2), now=now)

    assert {record.id for record in ranked} == {too_high.id, too_low.id}
    assert ranked[0].id == too_high.id, "clamped-high (1.0) must still beat clamped-low (0.0)"


# ---------------------------------------------------------------------------
# 7. Empty / whitespace-only query: no division-by-zero, no exceptions
# ---------------------------------------------------------------------------


def test_whitespace_only_query_yields_no_matches_without_crashing() -> None:
    now = datetime.now(UTC)
    record = _record(created_at=now)

    ranked = _rank_by_overlap([record], _request(query="   "), now=now)

    assert ranked == []


def test_punctuation_only_query_yields_no_matches_without_crashing() -> None:
    now = datetime.now(UTC)
    record = _record(created_at=now)

    ranked = _rank_by_overlap([record], _request(query="!!!???"), now=now)

    assert ranked == []


# ---------------------------------------------------------------------------
# 8. Timezone parity: naive and aware timestamps both work
# ---------------------------------------------------------------------------


def test_naive_and_aware_created_at_both_work_without_crashing() -> None:
    now = datetime.now(UTC)
    naive_record = MemoryRecord(
        id=str(uuid.uuid4()),
        namespace="ranking-test",
        content=CONTENT,
        tags=[],
        metadata={},
        created_at=datetime.now(),  # naive — no tzinfo
    )
    aware_record = _record(created_at=now)

    ranked = _rank_by_overlap([naive_record, aware_record], _request(limit=2), now=now)

    assert {record.id for record in ranked} == {naive_record.id, aware_record.id}


def test_naive_now_parameter_does_not_crash() -> None:
    record = _record(created_at=datetime.now(UTC))

    ranked = _rank_by_overlap([record], _request(), now=datetime.now())  # naive `now`

    assert ranked == [record]


# ---------------------------------------------------------------------------
# 9. Deterministic time: injected `now` produces stable, repeatable ranking
# ---------------------------------------------------------------------------


def test_injected_now_produces_deterministic_ranking() -> None:
    fixed_now = datetime(2026, 1, 1, tzinfo=UTC)
    newer = _record(performance_score=0.5, created_at=fixed_now - timedelta(days=1))
    older = _record(performance_score=0.5, created_at=fixed_now - timedelta(days=100))

    first = _rank_by_overlap([older, newer], _request(limit=2), now=fixed_now)
    second = _rank_by_overlap([older, newer], _request(limit=2), now=fixed_now)

    assert [record.id for record in first] == [record.id for record in second] == [
        newer.id,
        older.id,
    ]


# ---------------------------------------------------------------------------
# 10. Degradation parity: unusable metadata reduces to pre-Phase-A ordering
# ---------------------------------------------------------------------------


def test_degradation_parity_preserves_pre_phase_a_stable_ordering() -> None:
    now = datetime.now(UTC)
    record_a = _record(metadata_override={}, created_at=now)
    record_b = _record(metadata_override={"outcome": "malformed"}, created_at=now)

    # Equal overlap (identical content), equal neutral quality (both
    # unusable -> 0.5), equal recency (identical created_at) -> truly tied
    # final_score -> Python's stable sort preserves input order, exactly
    # matching what pre-Phase-A pure-overlap scoring would have done for
    # two equal-overlap records.
    forward = _rank_by_overlap([record_a, record_b], _request(limit=2), now=now)
    assert [record.id for record in forward] == [record_a.id, record_b.id]

    reversed_input = _rank_by_overlap([record_b, record_a], _request(limit=2), now=now)
    assert [record.id for record in reversed_input] == [record_b.id, record_a.id]


# ---------------------------------------------------------------------------
# Postgres parity — proving the same behavior reaches the real backend
# through the public search() path, not just the shared function directly.
# ---------------------------------------------------------------------------


async def _pg_pool(dsn: str):
    pool = await create_pool(dsn)
    await bootstrap_schema(pool)
    return pool


@pytest.mark.integration
def test_postgres_equal_overlap_higher_quality_ranks_first(test_database_url: str) -> None:
    async def run() -> None:
        pool = await _pg_pool(test_database_url)
        store = PostgresMemoryStore(pool)
        namespace = f"ranking-pg-{uuid.uuid4()}"
        try:
            low = await store.write(_record(performance_score=0.0, namespace=namespace))
            high = await store.write(_record(performance_score=1.0, namespace=namespace))

            results = await store.search(_request(namespace=namespace, limit=1))

            assert results[0].id == high.id
            assert low.id  # keep reference alive / documented as the loser
        finally:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM memories WHERE namespace = $1", namespace)
            await pool.close()

    asyncio.run(run())


@pytest.mark.integration
def test_postgres_strong_overlap_beats_weak_overlap(test_database_url: str) -> None:
    async def run() -> None:
        pool = await _pg_pool(test_database_url)
        store = PostgresMemoryStore(pool)
        namespace = f"ranking-pg-{uuid.uuid4()}"
        query = "wazuh alert repeated failed password attempts"
        try:
            weak = await store.write(
                _record(
                    "wazuh sent an alert about the lunch menu today",
                    performance_score=1.0,
                    namespace=namespace,
                )
            )
            strong = await store.write(
                _record(
                    "wazuh alert repeated failed password attempts were logged tonight",
                    performance_score=0.0,
                    namespace=namespace,
                )
            )

            results = await store.search(_request(query=query, namespace=namespace, limit=1))

            assert results[0].id == strong.id
            assert weak.id  # keep reference alive / documented as the loser
        finally:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM memories WHERE namespace = $1", namespace)
            await pool.close()

    asyncio.run(run())


def test_in_memory_store_search_uses_outcome_aware_ranking() -> None:
    """Sanity check that InMemoryMemoryStore.search() (the public path, not
    _rank_by_overlap directly) exhibits the same behavior."""

    async def run() -> None:
        store = InMemoryMemoryStore()
        namespace = "ranking-inmem"
        low = await store.write(_record(performance_score=0.0, namespace=namespace))
        high = await store.write(_record(performance_score=1.0, namespace=namespace))

        results = await store.search(_request(namespace=namespace, limit=1))

        assert results[0].id == high.id
        assert low.id

    asyncio.run(run())
