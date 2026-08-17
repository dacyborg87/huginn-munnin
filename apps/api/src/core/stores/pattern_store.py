"""PatternStore Protocol + in-memory, JSON-file, and Postgres implementations.

`outcomes` stays a JSONB array on the Postgres side, matching
`Pattern.outcomes: list[dict]` exactly — not normalized into a separate
table, per the approved design (nothing in the codebase queries individual
outcomes independently of their parent pattern).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Lock
from typing import Protocol

import asyncpg

from core.reasoning_types import Pattern


class PatternStore(Protocol):
    async def load(self) -> dict[str, Pattern]: ...

    async def save(self, patterns: dict[str, Pattern]) -> None: ...


class InMemoryPatternStore:
    def __init__(self) -> None:
        self._patterns: dict[str, Pattern] = {}
        self._lock = Lock()

    async def load(self) -> dict[str, Pattern]:
        with self._lock:
            return dict(self._patterns)

    async def save(self, patterns: dict[str, Pattern]) -> None:
        with self._lock:
            self._patterns = dict(patterns)


class JsonFilePatternStore:
    """The pre-persistence-milestone behavior (apps/api/data/reasoning_patterns.json),
    kept only as a read source for the migration utility — not used as a
    runtime backend by default anymore.
    """

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path

    async def load(self) -> dict[str, Pattern]:
        if not self.storage_path.exists():
            return {}
        try:
            raw_patterns = json.loads(self.storage_path.read_text())
        except json.JSONDecodeError:
            return {}
        return {
            raw["pattern_id"]: Pattern(**raw)
            for raw in raw_patterns
            if isinstance(raw, dict) and "pattern_id" in raw
        }

    async def save(self, patterns: dict[str, Pattern]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps([pattern.to_dict() for pattern in patterns.values()], indent=2)
        )


class PostgresPatternStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def load(self) -> dict[str, Pattern]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT pattern_id, context_signature, preferred_path_distribution, "
                "success_rate, conditions, matched_contexts, outcomes FROM reasoning_patterns"
            )
        patterns: dict[str, Pattern] = {}
        for row in rows:
            pattern_id = str(row["pattern_id"])
            pattern = Pattern(
                pattern_id=pattern_id,
                context_signature=_load_jsonb(row["context_signature"]),
                preferred_path_distribution=_load_jsonb(row["preferred_path_distribution"]),
                success_rate=row["success_rate"],
                conditions=_load_jsonb(row["conditions"]),
                matched_contexts=row["matched_contexts"],
                outcomes=_load_jsonb(row["outcomes"]),
            )
            patterns[pattern_id] = pattern
        return patterns

    async def save(self, patterns: dict[str, Pattern]) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for pattern in patterns.values():
                    await conn.execute(
                        """
                        INSERT INTO reasoning_patterns
                            (pattern_id, context_signature, preferred_path_distribution,
                             success_rate, conditions, matched_contexts, outcomes, updated_at)
                        VALUES ($1, $2::jsonb, $3::jsonb, $4, $5::jsonb, $6, $7::jsonb, now())
                        ON CONFLICT (pattern_id) DO UPDATE SET
                            context_signature = EXCLUDED.context_signature,
                            preferred_path_distribution = EXCLUDED.preferred_path_distribution,
                            success_rate = EXCLUDED.success_rate,
                            conditions = EXCLUDED.conditions,
                            matched_contexts = EXCLUDED.matched_contexts,
                            outcomes = EXCLUDED.outcomes,
                            updated_at = now()
                        """,
                        uuid.UUID(pattern.pattern_id),
                        json.dumps(pattern.context_signature, default=str),
                        json.dumps(pattern.preferred_path_distribution),
                        pattern.success_rate,
                        json.dumps(pattern.conditions, default=str),
                        pattern.matched_contexts,
                        json.dumps(pattern.outcomes, default=str),
                    )


def _load_jsonb(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value
