"""MemoryStore Protocol + in-memory and Postgres implementations.

The keyword-overlap ranking algorithm is defined once (`_rank_by_overlap`)
and used by both backends, so search behavior is identical regardless of
where records physically live — the Postgres backend filters by namespace
in SQL (a plain indexed equality match) and then applies the exact same
Python ranking the in-memory backend always has, rather than reimplementing
relevance scoring in SQL.

Phase A1 (outcome-aware ranking): keyword overlap remains the dominant,
primary signal. A bounded, centered adjustment derived from the memory's
recorded outcome quality (``metadata.outcome.performance_score``, already
written by the orchestrator on every pipeline-produced memory — see
``core/outcomes.py``) and its recency is added on top, but only ever to
records that already passed the existing relevance gate
(``exact_match or token_overlap > 0``) — that gate is unchanged, so an
otherwise-irrelevant memory can never be pulled in merely for being newer
or more successful. See ``core/stores/trace.py`` for the unrelated
trace-id correlation helpers Phase A2 reuses below.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol

import asyncpg

from core.stores.trace import extract_trace_id, trace_id_from_metadata
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest


class MemoryStore(Protocol):
    async def write(self, record: MemoryRecord) -> MemoryRecord: ...

    async def search(self, request: MemorySearchRequest) -> list[MemoryRecord]: ...

    async def find_by_trace_id(self, trace_id: str) -> list[MemoryRecord]: ...


# Phase A1 scoring constants. Kept small relative to overlap_score's [0, 1]
# range (plus exact-match forcing 1.0) so overlap stays the dominant signal;
# the combined adjustment magnitude tops out at 0.15*0.5 + 0.10*0.5 = 0.125,
# well under the 0.25+ overlap gaps a "strongly vs weakly relevant" pair
# will typically show.
QUALITY_WEIGHT = 0.15
RECENCY_WEIGHT = 0.10
RECENCY_HALF_LIFE_DAYS = 14.0


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _normalize_to_utc(value: datetime | None) -> datetime | None:
    """Defensively coerce a datetime to UTC-aware. Naive datetimes are
    assumed to already be UTC (matches how both stores always write
    ``created_at`` today) rather than raising on the classic
    "can't subtract offset-naive and offset-aware datetimes" error."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _extract_quality(record: MemoryRecord) -> float:
    """metadata.outcome.performance_score, clamped to [0, 1]; 0.5 (neutral,
    zero adjustment) for anything missing, malformed, or unusable — a
    memory with no outcome data or an unrecognized metadata shape (e.g. the
    reasoning-pattern-tagged writes, or arbitrary externally-authored
    metadata from POST /memory) must degrade to exactly today's plain
    overlap ranking, never crash and never be penalized for lacking data
    that isn't its fault."""
    metadata = record.metadata
    if not isinstance(metadata, dict):
        return 0.5
    outcome = metadata.get("outcome")
    if not isinstance(outcome, dict):
        return 0.5
    raw = outcome.get("performance_score")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return 0.5
    value = float(raw)
    if not math.isfinite(value):
        return 0.5
    return max(0.0, min(1.0, value))


def _extract_recency(record: MemoryRecord, now: datetime) -> float:
    """Bounded exponential decay in (0, 1], 1.0 at age zero. A missing
    ``created_at`` (not expected in practice — both stores always set it on
    write — but defensively possible on a hand-built MemoryRecord) yields
    the neutral midpoint, same treatment as missing quality data."""
    created_at = _normalize_to_utc(record.created_at)
    if created_at is None:
        return 0.5
    age_seconds = (now - created_at).total_seconds()
    age_days = max(0.0, age_seconds / 86400.0)
    return math.exp(-age_days / RECENCY_HALF_LIFE_DAYS)


def _rank_by_overlap(
    records: list[MemoryRecord],
    request: MemorySearchRequest,
    now: datetime | None = None,
) -> list[MemoryRecord]:
    now = _normalize_to_utc(now) if now is not None else datetime.now(UTC)

    query = request.query.lower()
    query_tokens = _tokens(query)
    scored_results: list[tuple[float, MemoryRecord]] = []

    for record in records:
        content = record.content.lower()
        record_tokens = _tokens(content)
        exact_match = query in content
        token_overlap = len(query_tokens & record_tokens) / max(len(query_tokens), 1)

        if exact_match or token_overlap > 0:
            overlap_score = 1.0 if exact_match else token_overlap
            quality = _extract_quality(record)
            recency = _extract_recency(record, now)
            adjustment = QUALITY_WEIGHT * (quality - 0.5) + RECENCY_WEIGHT * (recency - 0.5)
            final_score = overlap_score + adjustment
            scored_results.append((final_score, record))

    scored_results.sort(key=lambda result: result[0], reverse=True)
    return [record for _, record in scored_results[: request.limit]]


class InMemoryMemoryStore:
    """Today's exact MuninnMemory behavior, moved behind the MemoryStore protocol."""

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []
        self._lock = Lock()

    async def write(self, record: MemoryRecord) -> MemoryRecord:
        stored = record.model_copy(
            update={
                "id": record.id or str(uuid.uuid4()),
                "created_at": record.created_at or datetime.now(UTC),
            }
        )
        with self._lock:
            self._records.append(stored)
        return stored

    async def search(self, request: MemorySearchRequest) -> list[MemoryRecord]:
        with self._lock:
            candidates = [
                record
                for record in self._records
                if request.namespace is None or record.namespace == request.namespace
            ]
        return _rank_by_overlap(candidates, request)

    async def find_by_trace_id(self, trace_id: str) -> list[MemoryRecord]:
        """Phase A2: no separate trace_id storage — derived at read time
        from metadata, exactly mirroring what PostgresMemoryStore computes
        at write time, so both backends agree on which records match."""
        with self._lock:
            candidates = list(self._records)
        matches = []
        for record in candidates:
            derived = trace_id_from_metadata(record.metadata)
            if derived is not None and str(derived) == str(trace_id):
                matches.append(record)
        return matches


class PostgresMemoryStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def write(self, record: MemoryRecord) -> MemoryRecord:
        stored = record.model_copy(
            update={
                "id": record.id or str(uuid.uuid4()),
                "created_at": record.created_at or datetime.now(UTC),
            }
        )
        trace_id = trace_id_from_metadata(stored.metadata)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memories (id, namespace, content, tags, metadata, trace_id, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                """,
                uuid.UUID(stored.id),
                stored.namespace,
                stored.content,
                stored.tags,
                json.dumps(stored.metadata, default=str),
                trace_id,
                stored.created_at,
            )
        return stored

    async def search(self, request: MemorySearchRequest) -> list[MemoryRecord]:
        async with self._pool.acquire() as conn:
            if request.namespace is not None:
                rows = await conn.fetch(
                    "SELECT id, namespace, content, tags, metadata, created_at "
                    "FROM memories WHERE namespace = $1",
                    request.namespace,
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, namespace, content, tags, metadata, created_at FROM memories"
                )

        records = [_row_to_record(row) for row in rows]
        return _rank_by_overlap(records, request)

    async def find_by_trace_id(self, trace_id: str) -> list[MemoryRecord]:
        trace_uuid = extract_trace_id(trace_id)
        if trace_uuid is None:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, namespace, content, tags, metadata, created_at "
                "FROM memories WHERE trace_id = $1 ORDER BY created_at ASC",
                trace_uuid,
            )
        return [_row_to_record(row) for row in rows]


def _row_to_record(row: Any) -> MemoryRecord:
    return MemoryRecord(
        id=str(row["id"]),
        namespace=row["namespace"],
        content=row["content"],
        tags=list(row["tags"]),
        metadata=(
            json.loads(row["metadata"])
            if isinstance(row["metadata"], str)
            else dict(row["metadata"])
        ),
        created_at=row["created_at"],
    )
