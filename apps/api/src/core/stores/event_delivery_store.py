"""Opt-in PostgreSQL admission only: no fallback, dispatcher, or automatic retry.

Construct with a dedicated asyncpg pool after the existing schema bootstrap.
The caller owns the pool. No production route instantiates this store yet.
Callers must derive source/operation scope from trusted identity, retain the
same envelope/key for ambiguous commit failures, and configure pool timeouts.
There is deliberately no memory implementation or retry loop.
"""

from __future__ import annotations

import json
from typing import Protocol
from uuid import UUID, uuid4

import asyncpg

from core.event_delivery import (
    DeliveryConflict,
    DeliveryEnvelope,
    DeliveryRecord,
    DeliveryStorageError,
)


class DeliveryStore(Protocol):
    async def admit(self, envelope: DeliveryEnvelope) -> DeliveryRecord: ...

    async def get(self, delivery_id: UUID) -> DeliveryRecord | None: ...


class PostgresDeliveryStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def admit(self, envelope: DeliveryEnvelope) -> DeliveryRecord:
        payload, digest = envelope.encode()
        try:
            async with self._pool.acquire() as conn:  # noqa: SIM117 - keep commit boundary explicit
                async with conn.transaction(isolation="read_committed"):
                    row = await conn.fetchrow(
                        """INSERT INTO event_deliveries
                        (delivery_id, source, operation, idempotency_key, event_id, event_type,
                         payload, payload_hash, schema_version, trace_id, parent_id)
                        VALUES ($1,$2,$3,$4,$5,$6,$7::json,$8,$9,$10,$11)
                        ON CONFLICT (source, operation, idempotency_key) DO NOTHING
                        RETURNING *""",
                        uuid4(),
                        envelope.source,
                        envelope.operation,
                        envelope.idempotency_key,
                        envelope.event_id,
                        envelope.event_type,
                        payload,
                        digest,
                        envelope.schema_version,
                        envelope.trace_id,
                        envelope.parent_id,
                    )
                    if row is None:
                        # A separate READ COMMITTED statement sees the winner after
                        # INSERT's uniqueness wait, including concurrent admissions.
                        row = await conn.fetchrow(
                            """SELECT * FROM event_deliveries
                            WHERE source=$1 AND operation=$2 AND idempotency_key=$3""",
                            envelope.source,
                            envelope.operation,
                            envelope.idempotency_key,
                        )
                        if row is None:
                            raise DeliveryStorageError("Delivery could not be confirmed")
                        existing = _record(row)
                        old_payload, _ = existing.envelope.encode()
                        if old_payload != payload or any(
                            getattr(existing.envelope, field) != getattr(envelope, field)
                            for field in (
                                "event_id",
                                "event_type",
                                "schema_version",
                                "trace_id",
                                "parent_id",
                            )
                        ):
                            raise DeliveryConflict("Scoped idempotency key conflicts")
                    record = _record(row)
            # Do not return until transaction commit and connection release finish.
            return record
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
            raise DeliveryStorageError(
                "Durable admission not confirmed; retry the same key"
            ) from None

    async def get(self, delivery_id: UUID) -> DeliveryRecord | None:
        if not isinstance(delivery_id, UUID):
            raise TypeError("delivery_id must be a UUID")
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM event_deliveries WHERE delivery_id=$1", delivery_id
                )
            return _record(row) if row else None
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
            raise DeliveryStorageError("Delivery retrieval unavailable") from None


def _record(row) -> DeliveryRecord:
    payload = row["payload"]
    return DeliveryRecord(
        delivery_id=row["delivery_id"],
        envelope=DeliveryEnvelope(
            source=row["source"],
            operation=row["operation"],
            idempotency_key=row["idempotency_key"],
            event_id=row["event_id"],
            event_type=row["event_type"],
            payload=json.loads(payload) if isinstance(payload, str) else payload,
            schema_version=row["schema_version"],
            trace_id=row["trace_id"],
            parent_id=row["parent_id"],
        ),
        payload_hash=row["payload_hash"],
        state=row["state"],
        attempt_count=row["attempt_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
