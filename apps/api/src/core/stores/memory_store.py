"""MemoryStore Protocol + in-memory and Postgres implementations.

The keyword-overlap ranking algorithm is defined once (`_rank_by_overlap`)
and used by both backends, so search behavior is identical regardless of
where records physically live — the Postgres backend filters by namespace
in SQL (a plain indexed equality match) and then applies the exact same
Python ranking the in-memory backend always has, rather than reimplementing
relevance scoring in SQL.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol

import asyncpg

from core.stores.trace import trace_id_from_metadata
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest


class MemoryStore(Protocol):
    async def write(self, record: MemoryRecord) -> MemoryRecord: ...

    async def search(self, request: MemorySearchRequest) -> list[MemoryRecord]: ...


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _rank_by_overlap(
    records: list[MemoryRecord], request: MemorySearchRequest
) -> list[MemoryRecord]:
    query = request.query.lower()
    query_tokens = _tokens(query)
    scored_results: list[tuple[float, MemoryRecord]] = []

    for record in records:
        content = record.content.lower()
        record_tokens = _tokens(content)
        exact_match = query in content
        token_overlap = len(query_tokens & record_tokens) / max(len(query_tokens), 1)

        if exact_match or token_overlap > 0:
            score = 1.0 if exact_match else token_overlap
            scored_results.append((score, record))

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

        records = [
            MemoryRecord(
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
            for row in rows
        ]
        return _rank_by_overlap(records, request)
