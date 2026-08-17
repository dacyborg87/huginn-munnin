"""Shared asyncpg pool + idempotent schema bootstrap.

One pool is created per process and handed to all four Postgres store
implementations — connection management lives in exactly one place rather
than being scattered across stores.
"""

from __future__ import annotations

from pathlib import Path

import asyncpg

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema.sql"


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)


async def bootstrap_schema(pool: asyncpg.Pool) -> None:
    """Apply schema.sql. Uses CREATE TABLE/INDEX IF NOT EXISTS — safe to
    call on every startup, no migration framework involved."""
    statement = SCHEMA_PATH.read_text()
    async with pool.acquire() as conn:
        await conn.execute(statement)
