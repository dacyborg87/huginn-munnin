# Muninn Persistence Foundation

This document covers the persistence milestone that turned Muninn from
process-local working memory into memory that survives a restart, without
redesigning the reasoning engine (`decision_engine.py`, `intelligence_graph.py`)
or the Security Knowledge Graph (`core/knowledge_graph.py`, unrelated —
see [architecture.md](architecture.md) for the distinction between the two
"graph" systems in this project).

## CURRENTLY IMPLEMENTED

**Five persistent stores**, each behind a `typing.Protocol` with an
in-memory backend (default) and a Postgres backend (`asyncpg`, plain SQL,
no ORM):

| Concern | Protocol | In-memory | Postgres |
|---|---|---|---|
| Muninn memory records | `MemoryStore` | `InMemoryMemoryStore` | `PostgresMemoryStore` |
| Outcome history + learned weights | `OutcomeStore` | `InMemoryOutcomeStore` | `PostgresOutcomeStore` |
| Full system event log | `SystemLogStore` | `InMemorySystemLogStore` | `PostgresSystemLogStore` |
| Reasoning patterns | `PatternStore` | `InMemoryPatternStore` | `PostgresPatternStore` |

All four live under `apps/api/src/core/stores/`. `MuninnMemory`,
`OutcomeTracker`, `EventBus`, and `ReasoningPatternEngine` depend only on
these Protocols — never on `asyncpg` directly — via a `store` constructor
argument (defaulting to the in-memory implementation) and a `bind_store()`
method used to swap backends at startup.

**Backend selection** happens in exactly one place:
`Settings.persistence_backend` (`"memory"` default, or `"postgres"`) is read
once by `huginn_muninn_api.core.persistence.build_stores()`, called once
from `main.py`'s `lifespan()` at startup. Nothing else branches on backend.

**Postgres schema** (`apps/api/schema.sql`, plain idempotent SQL —
`CREATE TABLE/INDEX IF NOT EXISTS`, no migration framework):

- `memories` — namespace, content, tags (`TEXT[]`, GIN-indexed), metadata (JSONB), trace_id
- `system_events` — event_type, payload (JSONB), trace_id, indexed on event_type and created_at
- `outcomes` — own `id` primary key (not `event_id` — a plain indexed column), trace_id, chosen_path
- `learned_weights` — `path` primary key, the sole authoritative source for path weights
- `reasoning_patterns` — outcomes stays a JSONB array, matching `Pattern.outcomes: list[dict]` exactly; not normalized into a sixth table

No foreign keys — the four subsystems are independent in the Python code
today, so the schema doesn't invent a relationship that doesn't exist.

**`trace_id`** is a correlation id only, derived from data the orchestrator
already threads through every event payload (`command_event_id`) and memory
metadata — no `EventType`, event payload shape, or `MemoryRecord` field was
changed to add it. See `core/stores/trace.py`.

**Learned weights are now single-sourced.** The old indirection — where
`OutcomeTracker`'s weights were reconstructed by searching Muninn memory
records tagged `"learning_weights"` — is gone. The flow is now:

```
Postgres learned_weights table
    -> OutcomeTracker in-process cache (loaded once via hydrate() at startup,
       kept in sync on every record())
    -> DecisionEngine (unchanged scoring math)
```

The redundant `MemoryRecord` write that used to exist solely to make that
reconstruction possible has been removed from `orchestrator.py`. The
`decision_engine.py` weight math itself — `+0.1` success, `-0.2` failure,
`-0.05` partial, clamped to `[-0.6, 0.6]` — is untouched.

**Test strategy**: the existing 121-test suite passes unchanged against the
in-memory default (still the default, still requires no database). 11 new
tests: 8 store contract tests (4 concerns × 2 backends, in-memory always
runs, Postgres self-skips without `TEST_DATABASE_URL`), the mandatory
restart test, the mandatory behavioral-routing-persistence test, and an
event-shape parity regression test guaranteeing the dashboard's `/events`
contract is unaffected by backend choice.

**Migration utility** (`apps/api/scripts/migrate_reasoning_patterns.py`):
non-destructive, idempotent upsert of the existing
`apps/api/data/reasoning_patterns.json` into Postgres. Never modifies or
deletes the source file. Not run automatically.

## NEXT MILESTONE (not built yet)

- Wiring `docker-compose.yml`'s Postgres service into the actual deployed
  runtime path (right now it's opt-in local infrastructure for anyone who
  sets `persistence_backend=postgres`; nothing forces it on).
- Namespacing/scoping decisions for `learned_weights` and
  `reasoning_patterns` if multi-tenant or multi-project use ever becomes a
  real requirement (both are intentionally global today, matching the
  pre-persistence in-memory behavior exactly).
- Any use of `trace_id` beyond storage — e.g., a `/trace/{id}` endpoint that
  reconstructs a full reasoning flow across all four tables. Not built; the
  column exists so this becomes possible later without another schema
  change.

## LONG-TERM VISION (architectural, not started)

Everything in `docs/architecture.md`'s later phases remains exactly as
speculative as before this milestone: no LLM, no embeddings, no vector
search, no ChromaDB, no graph-memory system connecting Event → Reasoning
Context → Decision → Action → Outcome → Memory → Future Recall as an actual
traversable structure. `trace_id` is a deliberate, minimal step toward that
future lineage — a correlation id, not a graph edge — and this milestone
does not build the graph.

## Backend Selection — How To Use It

Default (no config needed):

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:anyio --ignore=tests/test_graph_intelligence.py -q
```

To run with Postgres:

```bash
docker compose up -d postgres
cd apps/api
echo "PERSISTENCE_BACKEND=postgres" >> .env   # or export PERSISTENCE_BACKEND=postgres
PYTHONPATH=src uvicorn huginn_muninn_api.main:app --reload
```

To run the Postgres-backed test suite (skipped otherwise):

```bash
docker compose up -d postgres
TEST_DATABASE_URL=postgresql://muninn:muninn@localhost:5432/muninn \
    PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:anyio --ignore=tests/test_graph_intelligence.py -q
```

## What Is Still NOT Implemented

- The API does not run with Postgres by default — `persistence_backend`
  defaults to `"memory"`, matching every prior milestone's behavior.
- No connection retry/backoff if Postgres is unreachable at startup with
  `persistence_backend=postgres` set — `build_stores()` will raise and the
  app will fail to start, which is the correct behavior for this milestone
  (fail loud, don't silently fall back to in-memory and hide data loss) but
  is worth knowing before wiring this into any automated deployment.
- No per-namespace scoping for `learned_weights` or `reasoning_patterns` —
  both remain global, exactly matching pre-persistence behavior.
- No admin/cleanup tooling for the Postgres tables (no TTL, no pruning of
  old `system_events` rows) — they grow unbounded, same risk profile the
  in-memory lists always had, just now durable instead of bounded by
  process restarts.
