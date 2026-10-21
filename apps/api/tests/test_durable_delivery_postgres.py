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
