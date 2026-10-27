# Persistence, Durable Admission, and Lease Recovery

Implementation baseline: Phase 3B.2, commit `9371666`. This guide distinguishes stored investigation data from reliable delivery. See [architecture](architecture.md) for component relationships and the [README](../README.md) for local setup.

## Persistence Boundaries

| Data | Implementation | Restart behavior |
| --- | --- | --- |
| Security graph, graph summary, evidence index | Local JSON with an ingestion lock and atomic per-file replacement | Preserved if the same artifact files remain available |
| Latest ingestion batch | Directly written pipeline report JSON | File survives, but is not a complete or atomic event log |
| Reasoning memory, outcomes, weights, patterns, system event log | In-memory default or optional PostgreSQL | PostgreSQL records survive; in-memory records do not |
| EventBus pending work | In-process asyncio queue in both backend modes | No crash recovery or automatic replay |
| Delivery records | Separate PostgreSQL `event_deliveries` table | Recoverable by explicit store calls; no automatic handler dispatch |

The security graph is unrelated to the reasoning state-transition graph. Changing `PERSISTENCE_BACKEND` does not move graph/evidence files into PostgreSQL.

## Reasoning Store Selection

Four [store interfaces](../apps/api/src/core/stores) cover five PostgreSQL tables:

| Interface | Tables |
| --- | --- |
| `MemoryStore` | `memories` |
| `SystemLogStore` | `system_events` |
| `OutcomeStore` | `outcomes`, `learned_weights` |
| `PatternStore` | `reasoning_patterns` |

[build_stores](../apps/api/src/huginn_muninn_api/core/persistence.py) runs during FastAPI lifespan startup, selects the backend, and supplies stores to the EventBus and orchestrator. `memory` is the default. With `postgres`, startup creates a pool, applies schema, and hydrates reasoning state. Connection/bootstrap failure aborts startup; it does not silently fall back to memory.

Settings are `PERSISTENCE_BACKEND`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. Runtime settings construct the DSN; `DATABASE_URL` is used by the manual pattern-migration utility, not as a replacement for these runtime settings. Do not commit credentials to `.env` or shell examples. The current DSN builder interpolates credentials without URL escaping, so reserved characters require care until separately corrected.

For an already provisioned, approved local database, export those PostgreSQL settings through your local secret mechanism, then start from `apps/api`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src PERSISTENCE_BACKEND=postgres \
  .venv/bin/python -m uvicorn huginn_muninn_api.main:app \
  --host 127.0.0.1 --port 8000 --workers 1
```

This startup **can change database schema**. Read the bootstrap precautions first. Compose defaults are not a hardened deployment: known development credentials, broad host bindings, and an unused ChromaDB service are present. Do not start the whole Compose stack just to run tests.

EventBus storage failures prevent handler dispatch for that event; handler failures are contained and counted, with no automatic retry. Acceptance is still best-effort in-memory, not durable delivery. A system-event log row records an event, not proof that every handler completed. Health reports worker state, not a database readiness probe.

Outcome-aware memory ranking and Python trace reconstruction are implemented. `trace_id` correlates memories, events, and outcomes; it is not a graph edge or a durable-delivery receipt. No public trace reconstruction endpoint is implemented. Learned weights and reasoning patterns remain global rather than tenant-scoped.

## Durable Admission Contract

The [delivery model](../apps/api/src/core/event_delivery.py) and [store](../apps/api/src/core/stores/event_delivery_store.py) are independent of EventBus and all production ingestion routes. Construct `PostgresDeliveryStore` with a caller-owned asyncpg pool after schema bootstrap. Configure connection, acquisition, and query deadlines in the caller; the store itself does not impose a universal operation deadline.

`DeliveryEnvelope` contains source, operation, idempotency key, source event ID, event type, JSON-object payload, schema version, and optional trace/parent identifiers. Validation requires nonempty bounded identifiers, schema version 1, valid UTF-8 finite JSON values, and at most 262144 encoded payload bytes. Canonical serialization sorts object keys; SHA-256 identifies the canonical payload.

`event_deliveries` stores a delivery UUID, the envelope, payload hash, state, attempts, creation/update timestamps, worker ID, lease token, lease expiry, and availability timestamp. The payload uses PostgreSQL JSON to preserve numeric representations used by admission identity.

`admit(envelope)` uses a transaction and database uniqueness on `(source, operation, idempotency_key)`:

- Same scope/key and equivalent payload plus event metadata returns the original delivery record.
- Conflicting payload or metadata raises `DeliveryConflict`.
- Different source or operation scopes admit independently.
- Key order is insignificant; array order, numeric representation (`1` versus `1.0`), and envelope metadata remain significant.
- Concurrent admissions are resolved by the database constraint, not only a preliminary read.
- The result is returned only after commit and connection release succeed.

Invalid envelopes raise `DeliveryValidationError`. Unavailable storage or an unconfirmed commit raises sanitized `DeliveryStorageError`, with no memory fallback. A lost response can leave commit outcome ambiguous; retain the same envelope and idempotency key for a caller-initiated retry. Retain stored records/keys for the promised retry window; no retention policy is implemented.

`get(delivery_id)` returns the persisted record or `None`. Fresh-process retrieval is verified. Future callers must derive scopes from trusted identity; the storage API does not provide authentication. Existing `/chat`, `/memory`, and ingestion response contracts are unchanged, and there is no new HTTP durable-admission endpoint.

## Claiming and State Transitions

`claim(worker_id, lease_seconds=30.0, source=None)` returns one eligible record or `None`. Lease duration must be positive, finite, and at most 86400 seconds. Source filtering is optional; callers must apply the intended scope. This is an internal store API, not a tenant authorization boundary.

| From | Condition | To | Ownership/attempt effect |
| --- | --- | --- | --- |
| `pending` | `available_at` is due | `processing` | New token and worker; attempts increment |
| `retry_scheduled` | `available_at` is due | `processing` | New token and worker; attempts increment |
| `processing` | Lease expired | `processing` | Replace owner/token; attempts increment |
| `processing` | Valid worker/token and unexpired lease | `completed` | Clear lease fields; retain attempt count |

`retry_scheduled` and `dead_lettered` are supported schema states, but there is no store operation implementing retry scheduling or dead-letter policy. Completed and dead-lettered records are not claim candidates.

Claims use a short READ COMMITTED transaction with `FOR UPDATE SKIP LOCKED`, ordered by creation time and delivery ID. Eligibility and expiry use `clock_timestamp()` from PostgreSQL, not application clocks. Ownership is committed before the method returns; processing does not hold the claim transaction open. Locked or unavailable work is skipped, so `None` does not prove the entire table is empty.

`complete(delivery_id, worker_id, lease_token)` acquires the row lock before checking database time, then conditionally updates a processing record with matching, unexpired ownership. Incorrect, expired, replaced, or repeated completion raises `DeliveryOwnershipError`. This protects against a stale worker marking another worker's claim complete.

## Crash Recovery and Guarantees

When a worker crashes after claiming, its row remains `processing` until expiry makes it eligible for another explicit `claim` call. The next claim preserves the delivery/envelope, increments attempts, and issues a different token. The old owner cannot complete it. A temporary diagnostic verified abrupt child-process exit, actual lease expiry, two competing recovery callers, stale-token rejection, and successful completion by the new owner.

A failed claim transaction rolls back ownership/attempt changes. If commit succeeds but its response is lost, the claim can remain owned until expiry; no internal retry is performed. Handler failure has no delivery-store transition yet because the store does not execute handlers. Without a recovery caller, expired work remains stored but unprocessed.

This is a foundation for future **at-least-once processing**, not an implemented end-to-end guarantee. A worker can perform an external action, lose its lease or crash before completion, and have another worker repeat the action. Tokens fence database completion, not those external side effects.

Not implemented: automatic durable dispatch, startup replay, lease renewal, complete retry execution policies, dead-letter handling, complete handler-side-effect deduplication, end-to-end delivery guarantees, or exactly-once external execution. Do not wire existing handlers into a claim loop without separate design and validation of these concerns.

## PostgreSQL Bootstrap and Schema Evolution

[schema.sql](../apps/api/schema.sql) is applied by [bootstrap_schema](../apps/api/src/core/stores/postgres_pool.py) during PostgreSQL-backed application startup or by explicit test/setup calls. There is no versioned migration framework. It creates the reasoning tables and the independent delivery table; `system_events` is not repurposed as a queue.

Phase 3B.2 adds lease/scheduling columns and replaces the original pending-only, zero-attempt delivery constraints inside an atomic `DO` block. It uses a transaction-scoped advisory lock and sets a five-second lock-acquisition timeout. State/attempt/lease constraints are revalidated, and eligibility/expiry/token indexes are created. Processing rows require ownership fields; non-processing rows must have no active lease fields.

Compatibility was tested by applying the prior committed schema from `1b945db`, inserting synthetic admission and system-event records, then applying the new schema. Those records were preserved. Repeated bootstrap also preserved completed delivery records. Arbitrarily drifted schemas and large-table deployment performance were not validated.

Operational precautions:

1. Verify the target database identity and ownership; keep a verified backup before changing a non-disposable database.
2. Inspect drift against the previously committed schema. `IF NOT EXISTS` does not reconcile incompatible existing columns or constraints.
3. Apply during a maintenance window with competing workers stopped. `ALTER TABLE` requires exclusive locks, and ordinary index creation can block writes.
4. Repeated startup still replaces/revalidates constraints; this is not a zero-work or zero-downtime migration. The five-second lock timeout limits waiting for locks, not total scan/index runtime.
5. Validate existing row counts, admission retrieval, constraints, and claim behavior afterward. A failure must be investigated, not bypassed by deleting records or relaxing constraints.

The SQL header and bootstrap helper contain some historical table-count/`CREATE IF NOT EXISTS` descriptions; the actual schema now includes delivery constraint evolution as described here. Those source comments are not changed by this documentation-only milestone.

The separate [reasoning-pattern migration utility](../apps/api/scripts/migrate_reasoning_patterns.py) reads legacy JSON and upserts patterns by ID. It preserves the source file but can update matching database rows. It is not a delivery migration, does not import historical events, and is not automatic. Preview from `apps/api` without a database connection:

```bash
.venv/bin/python scripts/migrate_reasoning_patterns.py --dry-run
```

Actual migration requires `DATABASE_URL` and separate target verification/approval. Do not run it against an existing database as part of routine tests.

## Isolated PostgreSQL Tests

Use PostgreSQL 16 with unique test-owned container/volume names, random test-only credentials, loopback-only port binding, no repository bind mounts, and synthetic records only. Verify resource labels, mounts, database/user identities, and the chosen port before execution. Never reuse an existing development or production volume. Cleanup must target only verified test-owned resources.

Use **two separate disposable databases**:

| Setting | Purpose |
| --- | --- |
| `TEST_DATABASE_URL` | Legacy reasoning/store integration tests; fixtures can delete rows |
| `HM_DELIVERY_TEST_DSN` | Dedicated delivery integration database; must not equal the legacy test database |
| `HM_DELIVERY_TEST_TOKEN` | Exactly 12 lowercase hexadecimal characters |

The delivery DSN must use `127.0.0.1`, no query string, and both username and database name `hm_admission_<token>`. The tests verify those identities. Do not log credentials. Delivery fixtures insert a synthetic system-event type that legacy enum-based readers cannot deserialize; sharing the databases produced four failures during validation. Separate databases resolved that fixture contamination without application changes.

After provisioning and exporting verified test DSNs through your local environment, run from `apps/api`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -B -m pytest \
  tests/test_event_delivery.py tests/test_durable_delivery_postgres.py \
  -p no:cacheprovider -q -rs
```

For the full safe selection, use the four explicit deselections in the [README](../README.md#safe-default-regression-run), but omit its `env -u TEST_DATABASE_URL -u HM_DELIVERY_TEST_DSN` prefix so the two verified test DSNs remain available. Keep bytecode disabled and the pytest cache disabled. Missing DSNs skip their respective integration tests, not proof of PostgreSQL correctness.

The four excluded report-writing tests must run in a temporary source/fixture/report copy, never the protected investigation checkout. Select their exact test IDs from the README without `--deselect=`. They modify reports even with bytecode/cache writes disabled. Compare canonical artifact hashes and Git status before and after validation.

## Recorded Validation

Phase 2 validation on 2026-10-27 tested the exact contents subsequently committed as `9371666`. No backend tests or frontend builds were rerun to create this documentation.

| Check | Result |
| --- | --- |
| Discovery | 278 backend tests |
| Safe suite without database DSNs | 253 passed, 21 skipped, 4 deselected |
| Safe suite with separate isolated PostgreSQL databases | 274 passed, 0 failed, 0 skipped, 4 deselected |
| Four report-writing tests in a temporary copy | 4 passed |
| Focused admission/lease tests | 41 passed; subset of backend results |
| Temporary worker-crash diagnostic | Passed |
| Ruff / Git whitespace checks | Passed |
| Frontend lint / TypeScript / Next.js production build | Passed |
| Canonical investigation artifacts | All 23 checksums unchanged |

All 278 discovered tests passed across isolated runs, not one combined invocation. Tests cover admission races, conflicting keys, independent scopes, failed commits, fresh-process retrieval, 16-way claims, 12-way expired-lease recovery, scheduling eligibility, wrong/stale/repeated completion, skipped row locks, interrupted database connections, and prior/repeated schema compatibility. Existing EventBus, API, graph, evidence, and Wazuh/GuardDuty regression tests passed.

Environment: Python 3.11.15, pytest 9.1.1, asyncpg 0.30.0, PostgreSQL 16, Node.js 22.23.1, npm 10.9.8, Next.js 15.5.18, ESLint 9.39.4. Backend runs reported a Starlette/AnyIO deprecation warning; frontend lint reported `next lint` deprecation. Dependency consistency passed, but this is not a vulnerability certification or a Python dependency lockfile.

## Security and Remaining Operational Limits

- No API authentication/authorization; trusted store scopes must not become user-controlled authorization bypasses.
- Development database credentials and broadly published Compose ports require hardening before deployment. Use least-privilege application roles and separate migration privileges.
- Existing ingestion endpoints can return raw exception details; delivery-store failures are sanitized, but that does not sanitize the entire API.
- Payloads may contain sensitive security information. SQL parameterization prevents value interpolation attacks in the delivery operations; it does not provide encryption, access controls, redaction, or retention management.
- No automatic delivery retry, dead-letter execution, retention cleanup, universal operation deadlines, or tenant isolation for global reasoning weights/patterns.
- JSON persistence is local-filesystem oriented and not a multi-file transaction. The latest-batch report has weaker write guarantees than the protected graph/evidence artifacts.
- Production deployment and automatic workflow processing are not approved. Keep demonstrations loopback-only and synthetic.
