"""Opt-in admission and explicit leases: no dispatcher or automatic retry.

Construct with a dedicated asyncpg pool after the existing schema bootstrap.
The caller owns the pool. No production route instantiates this store yet.
Callers must derive source/operation scope from trusted identity, retain the
same envelope/key for ambiguous commit failures, and configure pool timeouts.
There is deliberately no memory implementation or retry loop.
"""

from __future__ import annotations

import json
import math
from typing import Protocol
from uuid import UUID, uuid4

import asyncpg

from core.event_delivery import (
    DeliveryConflict,
    DeliveryEnvelope,
    DeliveryOwnershipError,
    DeliveryRecord,
    DeliveryStorageError,
)


class DeliveryStore(Protocol):
    async def admit(self, envelope: DeliveryEnvelope) -> DeliveryRecord: ...

    async def get(self, delivery_id: UUID) -> DeliveryRecord | None: ...

    async def claim(
        self, worker_id: str, *, lease_seconds: float = 30.0, source: str | None = None
    ) -> DeliveryRecord | None: ...

    async def complete(
        self, delivery_id: UUID, worker_id: str, lease_token: UUID
    ) -> DeliveryRecord: ...


class PostgresDeliveryStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def claim(
        self, worker_id: str, *, lease_seconds: float = 30.0, source: str | None = None
    ) -> DeliveryRecord | None:
        """Commit one claim, including explicit expired-lease recovery.

        No processing occurs here. An ambiguously committed claim is left to
        expire; this method never retries it. Pool timeouts bound DB waits.
        """
        _identifier(worker_id)
        if source is not None:
            _identifier(source)
        if (
            type(lease_seconds) not in (int, float)
            or not math.isfinite(lease_seconds)
            or not 0 < lease_seconds <= 86400
        ):
            raise ValueError("Lease duration must be positive and at most 86400 seconds")
        try:
            async with self._pool.acquire() as conn:  # noqa: SIM117 - explicit commit boundary
                async with conn.transaction(isolation="read_committed"):
                    row = await conn.fetchrow(
                        """WITH candidate AS (
                            SELECT delivery_id FROM event_deliveries
                            WHERE ($1::text IS NULL OR source=$1) AND (
                              (state IN ('pending','retry_scheduled')
                               AND available_at <= clock_timestamp())
                              OR (state='processing' AND lease_expires_at <= clock_timestamp()))
                            ORDER BY created_at, delivery_id
                            FOR UPDATE SKIP LOCKED LIMIT 1
                        )
                        UPDATE event_deliveries d SET state='processing',
                            attempt_count=d.attempt_count+1, worker_id=$2, lease_token=$3,
                            lease_expires_at=clock_timestamp()+$4::double precision*interval '1 second',
                            updated_at=clock_timestamp()
                        FROM candidate c WHERE d.delivery_id=c.delivery_id RETURNING d.*""",
                        source,
                        worker_id,
                        uuid4(),
                        lease_seconds,
                    )
                    record = _record(row) if row else None
            return record
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
            raise DeliveryStorageError("Delivery claim not confirmed") from None

    async def complete(
        self, delivery_id: UUID, worker_id: str, lease_token: UUID
    ) -> DeliveryRecord:
        """Reject expired, stale, and repeated completion with a conditional update."""
        _identifier(worker_id)
        if not isinstance(delivery_id, UUID) or not isinstance(lease_token, UUID):
            raise TypeError("Delivery and lease identifiers must be UUIDs")
        try:
            async with self._pool.acquire() as conn:  # noqa: SIM117 - explicit commit boundary
                async with conn.transaction(isolation="read_committed"):
                    # Check database time AFTER acquiring the row lock, not before
                    # a possible lock wait that might outlast the lease.
                    await conn.fetchval(
                        "SELECT delivery_id FROM event_deliveries WHERE delivery_id=$1 FOR UPDATE",
                        delivery_id,
                    )
                    row = await conn.fetchrow(
                        """UPDATE event_deliveries SET state='completed', worker_id=NULL,
                        lease_token=NULL, lease_expires_at=NULL, updated_at=clock_timestamp()
                        WHERE delivery_id=$1 AND state='processing' AND worker_id=$2
                        AND lease_token=$3 AND lease_expires_at > clock_timestamp()
                        RETURNING *""",
                        delivery_id,
                        worker_id,
                        lease_token,
                    )
                    if row is None:
                        raise DeliveryOwnershipError("Delivery ownership is not valid")
                    record = _record(row)
            return record
        except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError):
            raise DeliveryStorageError("Delivery completion not confirmed") from None

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
        worker_id=row["worker_id"],
        lease_token=row["lease_token"],
        lease_expires_at=row["lease_expires_at"],
        available_at=row["available_at"],
    )


def _identifier(value: str) -> None:
    if type(value) is not str or not value.strip() or len(value) > 256 or "\x00" in value:
        raise ValueError("Invalid worker or source identifier")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ValueError("Invalid worker or source identifier") from None
