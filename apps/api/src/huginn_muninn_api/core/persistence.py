"""Backend selection — the one place that decides in-memory vs Postgres.

Per the approved design: "Do not scatter backend-selection logic throughout
the application." main.py calls build_stores(settings) exactly once at
import time and injects the result into EventBus/Orchestrator; nothing else
branches on persistence_backend.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from core.stores.memory_store import InMemoryMemoryStore, MemoryStore, PostgresMemoryStore
from core.stores.outcome_store import InMemoryOutcomeStore, OutcomeStore, PostgresOutcomeStore
from core.stores.pattern_store import InMemoryPatternStore, PatternStore, PostgresPatternStore
from core.stores.postgres_pool import bootstrap_schema, create_pool
from core.stores.system_log_store import (
    InMemorySystemLogStore,
    PostgresSystemLogStore,
    SystemLogStore,
)
from huginn_muninn_api.core.config import Settings


@dataclass
class StoreBundle:
    memory_store: MemoryStore
    outcome_store: OutcomeStore
    system_log_store: SystemLogStore
    pattern_store: PatternStore
    pool: asyncpg.Pool | None = None

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()


async def build_stores(settings: Settings) -> StoreBundle:
    if settings.persistence_backend == "memory":
        return StoreBundle(
            memory_store=InMemoryMemoryStore(),
            outcome_store=InMemoryOutcomeStore(),
            system_log_store=InMemorySystemLogStore(),
            pattern_store=InMemoryPatternStore(),
        )

    pool = await create_pool(settings.postgres_dsn)
    await bootstrap_schema(pool)
    return StoreBundle(
        memory_store=PostgresMemoryStore(pool),
        outcome_store=PostgresOutcomeStore(pool),
        system_log_store=PostgresSystemLogStore(pool),
        pattern_store=PostgresPatternStore(pool),
        pool=pool,
    )
