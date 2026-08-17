"""One-time migration: apps/api/data/reasoning_patterns.json -> Postgres.

Non-destructive: reads the existing JSON file and upserts each pattern into
the reasoning_patterns table (ON CONFLICT DO UPDATE, by pattern_id — safe to
re-run). The source JSON file is never modified or deleted; it stays in
place as a backup after migration.

Not run automatically by anything — this is a manual, explicit step.

Usage:
    cd apps/api
    DATABASE_URL=postgresql://muninn:muninn@localhost:5432/muninn \
        .venv/bin/python scripts/migrate_reasoning_patterns.py

    # Point at a different source file:
    .venv/bin/python scripts/migrate_reasoning_patterns.py --source path/to/reasoning_patterns.json

    # See what would be migrated without writing anything:
    .venv/bin/python scripts/migrate_reasoning_patterns.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

API_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(API_SRC))

from core.stores.pattern_store import JsonFilePatternStore, PostgresPatternStore  # noqa: E402
from core.stores.postgres_pool import bootstrap_schema, create_pool  # noqa: E402


DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "data" / "reasoning_patterns.json"


async def migrate(source: Path, dsn: str, dry_run: bool) -> None:
    json_store = JsonFilePatternStore(source)
    patterns = await json_store.load()

    if not patterns:
        print(f"No patterns found at {source} — nothing to migrate.")
        return

    print(f"Read {len(patterns)} pattern(s) from {source}")
    for pattern_id, pattern in patterns.items():
        print(f"  - {pattern_id}  intent={pattern.context_signature.get('intent')!r}  "
              f"success_rate={pattern.success_rate}  outcomes={len(pattern.outcomes)}")

    if dry_run:
        print("\n--dry-run: not writing to Postgres. Source file untouched.")
        return

    pool = await create_pool(dsn)
    try:
        await bootstrap_schema(pool)
        pg_store = PostgresPatternStore(pool)
        await pg_store.save(patterns)
        print(f"\nUpserted {len(patterns)} pattern(s) into reasoning_patterns.")
        print(f"Source file left in place at {source} (not modified or deleted).")
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Path to reasoning_patterns.json (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be migrated without connecting to Postgres.",
    )
    args = parser.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not args.dry_run and not dsn:
        parser.error("DATABASE_URL must be set (unless --dry-run is used).")

    asyncio.run(migrate(args.source, dsn, args.dry_run))


if __name__ == "__main__":
    main()
