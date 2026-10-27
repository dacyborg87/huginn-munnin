"""Synthetic-only tests; never use the ordinary development database DSN.

Require HM_DELIVERY_TEST_DSN and HM_DELIVERY_TEST_TOKEN for a disposable DB
and user both named hm_admission_<token>. No production handlers are executed.
"""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg
import pytest

import core

# Keep imports isolated from legacy tests selecting repository-root core.
with patch.object(core, "__path__", [str(Path(__file__).parents[1] / "src/core"), *core.__path__]):
    from core.event_delivery import (
        DeliveryConflict,
        DeliveryEnvelope,
        DeliveryOwnershipError,
        DeliveryRecord,
        DeliveryStorageError,
    )
    from core.stores.event_delivery_store import PostgresDeliveryStore
    from core.stores.postgres_pool import bootstrap_schema

pytestmark = pytest.mark.integration


async def database():
    dsn = os.environ.get("HM_DELIVERY_TEST_DSN")
    token = os.environ.get("HM_DELIVERY_TEST_TOKEN", "")
    if not dsn:
        pytest.skip("Dedicated disposable admission database not configured")
    assert len(token) == 12 and all(c in "0123456789abcdef" for c in token)
    url = urlparse(dsn)
    assert url.hostname == "127.0.0.1" and not url.query
    assert url.username == url.path.lstrip("/") == "hm_admission_" + token
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8, command_timeout=5)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT current_database() AS db, current_user AS usr")
            assert row["db"] == row["usr"] == "hm_admission_" + token
        await bootstrap_schema(pool)
        return pool
    except BaseException:
        await pool.close()
        raise


def event():
    return DeliveryEnvelope(
        "synthetic-" + uuid4().hex,
        "admit",
        "stable-key",
        "source-event",
        "SYNTHETIC",
        {"nested": [1, "test"], "float": 1e20},
    )


def test_admission_idempotency_concurrency_and_scopes():
    async def run():
        pool = await database()
        try:
            store = PostgresDeliveryStore(pool)
            original = event()
            records = await asyncio.wait_for(
                asyncio.gather(*[store.admit(original) for _ in range(16)]), 10
            )
            assert len({r.delivery_id for r in records}) == 1
            async with pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM event_deliveries WHERE source=$1", original.source
                    )
                    == 1
                )
            record = records[0]
            assert record.state == "pending" and record.attempt_count == 0
            assert record.created_at == record.updated_at
            assert (await store.get(record.delivery_id)) == record
            assert await store.get(uuid4()) is None
            reordered = replace(original, payload=dict(reversed(list(original.payload.items()))))
            assert (await store.admit(reordered)) == record
            for altered in (
                replace(original, payload={"different": True}),
                replace(original, event_type="OTHER"),
            ):
                with pytest.raises(DeliveryConflict):
                    await store.admit(altered)
            assert (
                await store.admit(replace(original, source=original.source + "-other"))
            ).delivery_id != record.delivery_id
            assert (
                await store.admit(replace(original, operation="other"))
            ).delivery_id != record.delivery_id
            contested = replace(event(), idempotency_key="conflict-race")
            results = await asyncio.wait_for(
                asyncio.gather(
                    store.admit(contested),
                    store.admit(replace(contested, payload={"other": 1})),
                    return_exceptions=True,
                ),
                10,
            )
            assert sum(isinstance(r, DeliveryConflict) for r in results) == 1
            assert sum(isinstance(r, DeliveryRecord) for r in results) == 1
        finally:
            await pool.close()

    asyncio.run(run())


def test_commit_failure_rolls_back_without_acceptance():
    async def run():
        pool = await database()
        original = event()
        try:
            async with pool.acquire() as conn:
                await conn.execute("""CREATE FUNCTION reject_test_delivery() RETURNS trigger
                    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST_SECRET'; END $$;
                    CREATE CONSTRAINT TRIGGER reject_test_delivery
                    AFTER INSERT ON event_deliveries DEFERRABLE INITIALLY DEFERRED
                    FOR EACH ROW EXECUTE FUNCTION reject_test_delivery();""")
            with pytest.raises(DeliveryStorageError) as error:
                await PostgresDeliveryStore(pool).admit(original)
            assert "TEST_SECRET" not in str(error.value)
            async with pool.acquire() as conn:
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM event_deliveries WHERE source=$1", original.source
                    )
                    == 0
                )
                await conn.execute(
                    "DROP TRIGGER reject_test_delivery ON event_deliveries; DROP FUNCTION reject_test_delivery()"
                )
            assert (await PostgresDeliveryStore(pool).admit(original)).state == "pending"
        finally:
            await pool.close()

    asyncio.run(run())


def test_fresh_process_recovery():
    async def write():
        pool = await database()
        try:
            return await PostgresDeliveryStore(pool).admit(event())
        finally:
            await pool.close()

    record = asyncio.run(write())
    script = """
import asyncio, json, os, sys
from uuid import UUID
import asyncpg
from core.stores.event_delivery_store import PostgresDeliveryStore
async def run():
    pool = await asyncpg.create_pool(os.environ['HM_DELIVERY_TEST_DSN'], command_timeout=5)
    try:
        r = await PostgresDeliveryStore(pool).get(UUID(sys.argv[1]))
        print(json.dumps({'id': str(r.delivery_id), 'payload': r.envelope.payload, 'state': r.state}))
    finally:
        await pool.close()
asyncio.run(run())
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", script, str(record.delivery_id)],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert json.loads(child.stdout) == {
        "id": str(record.delivery_id),
        "payload": record.envelope.payload,
        "state": "pending",
    }


def test_unavailable_connection_has_no_memory_fallback():
    async def run():
        pool = await database()
        store = PostgresDeliveryStore(pool)
        await pool.close()
        with pytest.raises(DeliveryStorageError):
            await store.admit(event())
        with pytest.raises(DeliveryStorageError):
            await store.get(uuid4())

    asyncio.run(run())


def test_repeated_schema_preserves_existing_records():
    async def run():
        pool = await database()
        try:
            event_id = uuid4()
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO system_events(id,event_type,payload) VALUES($1,'SYNTHETIC','{}')",
                    event_id,
                )
            store = PostgresDeliveryStore(pool)
            record = await store.admit(event())
            await bootstrap_schema(pool)
            assert await store.get(record.delivery_id) == record
            async with pool.acquire() as conn:
                assert (
                    await conn.fetchval("SELECT count(*) FROM system_events WHERE id=$1", event_id)
                    == 1
                )
        finally:
            await pool.close()

    asyncio.run(run())


def test_concurrent_claim_and_completion():
    async def run():
        pool = await database()
        try:
            store = PostgresDeliveryStore(pool)
            original = event()
            admitted = await store.admit(original)
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[store.claim(f"worker-{i}", source=original.source) for i in range(16)]
                ),
                10,
            )
            owned = [r for r in results if r is not None]
            assert len(owned) == 1
            claim = owned[0]
            assert claim.delivery_id == admitted.delivery_id
            assert claim.state == "processing" and claim.attempt_count == 1
            assert claim.lease_token and claim.lease_expires_at > claim.updated_at
            async with pool.acquire() as conn, conn.transaction():
                # Successful NOWAIT proves claim returned after releasing locks.
                await conn.fetchrow(
                    "SELECT * FROM event_deliveries WHERE delivery_id=$1 FOR UPDATE NOWAIT",
                    claim.delivery_id,
                )
            for worker, token in [("wrong", claim.lease_token), (claim.worker_id, uuid4())]:
                with pytest.raises(DeliveryOwnershipError):
                    await store.complete(claim.delivery_id, worker, token)
            done = await store.complete(claim.delivery_id, claim.worker_id, claim.lease_token)
            assert done.state == "completed" and done.attempt_count == 1
            assert done.worker_id is done.lease_token is done.lease_expires_at is None
            with pytest.raises(DeliveryOwnershipError):
                await store.complete(claim.delivery_id, claim.worker_id, claim.lease_token)
            assert await store.claim("worker", source=original.source) is None
            assert (await store.admit(original)).delivery_id == done.delivery_id
            await bootstrap_schema(pool)
            assert await store.get(done.delivery_id) == done
        finally:
            await pool.close()

    asyncio.run(run())


def test_expired_lease_recovery_and_scheduling():
    async def run():
        pool = await database()
        try:
            store = PostgresDeliveryStore(pool)
            original = event()
            admitted = await store.admit(original)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE event_deliveries SET available_at=clock_timestamp()+interval '1 hour' WHERE delivery_id=$1",
                    admitted.delivery_id,
                )
            assert await store.claim("first", source=original.source) is None
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE event_deliveries SET state='retry_scheduled' WHERE delivery_id=$1",
                    admitted.delivery_id,
                )
            assert await store.claim("first", source=original.source) is None
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE event_deliveries SET available_at=clock_timestamp()-interval '1 second' WHERE delivery_id=$1",
                    admitted.delivery_id,
                )
            first = await store.claim("first", source=original.source, lease_seconds=60)
            async with pool.acquire() as conn:
                # Deterministic expiry without sleeping or relying on the app clock.
                await conn.execute(
                    "UPDATE event_deliveries SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE delivery_id=$1",
                    admitted.delivery_id,
                )
            with pytest.raises(DeliveryOwnershipError):
                await store.complete(first.delivery_id, first.worker_id, first.lease_token)
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[store.claim(f"recover-{i}", source=original.source) for i in range(12)]
                ),
                10,
            )
            recovered = [r for r in results if r is not None]
            assert len(recovered) == 1
            second = recovered[0]
            assert second.delivery_id == first.delivery_id and second.attempt_count == 2
            assert second.lease_token != first.lease_token
            assert second.envelope == first.envelope
            with pytest.raises(DeliveryOwnershipError):
                await store.complete(first.delivery_id, first.worker_id, first.lease_token)
            await store.complete(second.delivery_id, second.worker_id, second.lease_token)
            other = await store.admit(event())
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE event_deliveries SET state='dead_lettered' WHERE delivery_id=$1",
                    other.delivery_id,
                )
            assert await store.claim("worker", source=other.envelope.source) is None
        finally:
            await pool.close()

    asyncio.run(run())


def test_locked_candidate_skipped_and_rollback():
    async def run():
        pool = await database()
        try:
            store = PostgresDeliveryStore(pool)
            record = await store.admit(event())
            async with pool.acquire() as lock:
                tx = lock.transaction()
                await tx.start()
                try:
                    await lock.fetchval(
                        "SELECT delivery_id FROM event_deliveries WHERE delivery_id=$1 FOR UPDATE",
                        record.delivery_id,
                    )
                    assert (
                        await asyncio.wait_for(
                            store.claim("worker", source=record.envelope.source), 1
                        )
                        is None
                    )
                finally:
                    await tx.rollback()
            async with pool.acquire() as conn:
                await conn.execute("""CREATE FUNCTION reject_test_claim() RETURNS trigger
                    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'TEST_SECRET'; END $$;
                    CREATE CONSTRAINT TRIGGER reject_test_claim AFTER UPDATE ON event_deliveries
                    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION reject_test_claim();""")
            try:
                with pytest.raises(DeliveryStorageError) as error:
                    await store.claim("worker", source=record.envelope.source)
                assert "TEST_SECRET" not in str(error.value)
                assert await store.get(record.delivery_id) == record
            finally:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "DROP TRIGGER reject_test_claim ON event_deliveries; DROP FUNCTION reject_test_claim()"
                    )
            claim = await store.claim("worker", source=record.envelope.source)
            assert claim.attempt_count == 1
        finally:
            await pool.close()

    asyncio.run(run())


def test_database_connection_interrupted_during_claim():
    async def run():
        pool = await database()
        claimant = await asyncpg.create_pool(
            os.environ["HM_DELIVERY_TEST_DSN"], min_size=1, max_size=1, command_timeout=5
        )
        task = None
        try:
            record = await PostgresDeliveryStore(pool).admit(event())
            async with claimant.acquire() as conn:
                pid = await conn.fetchval("SELECT pg_backend_pid()")
            async with pool.acquire() as blocker:
                tx = blocker.transaction()
                await tx.start()
                try:
                    await blocker.execute("LOCK TABLE event_deliveries IN ACCESS EXCLUSIVE MODE")
                    task = asyncio.create_task(
                        PostgresDeliveryStore(claimant).claim(
                            "interrupted", source=record.envelope.source
                        )
                    )

                    async def wait_blocked():
                        while not await blocker.fetchval(
                            "SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=$1", pid
                        ):
                            await asyncio.sleep(0.01)

                    await asyncio.wait_for(wait_blocked(), 2)
                    assert await blocker.fetchval("SELECT pg_terminate_backend($1)", pid)
                    with pytest.raises(DeliveryStorageError):
                        await asyncio.wait_for(task, 3)
                finally:
                    await tx.rollback()
            assert await PostgresDeliveryStore(pool).get(record.delivery_id) == record
            claim = await PostgresDeliveryStore(claimant).claim(
                "reconnected", source=record.envelope.source
            )
            assert claim.attempt_count == 1
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await claimant.close()
            await pool.close()

    asyncio.run(run())
