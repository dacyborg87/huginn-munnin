-- Muninn Persistence Foundation schema.
--
-- Repeatable SQL with transactional delivery-constraint evolution.
-- No versioned migration framework. Applied via
-- huginn_muninn_api.core.persistence.bootstrap_schema() at startup when
-- persistence_backend="postgres", or manually with:
--
--   psql "$DATABASE_URL" -f schema.sql
--
-- Five tables, matching the five in-memory stores this milestone persists:
-- memories, system_events, outcomes, learned_weights, reasoning_patterns.
-- No foreign keys between them — the four subsystems (Muninn memory, event
-- log, outcome/weight tracking, reasoning patterns) are independent today in
-- the Python code, so the schema does not invent a relationship that does
-- not exist yet.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Admission foundation only. Apply this whole file through bootstrap_schema
-- to fresh or existing databases: CREATE IF NOT EXISTS adds this independent
-- table without updating, deleting, or importing historical records. It does
-- not reconcile an incompatible pre-existing table; inspect such drift before
-- deployment. Existing system_events and API contracts are unchanged.
-- JSON object key order/whitespace is ignored for admission identity; array
-- order, numeric representations (1 versus 1.0), and envelope metadata matter.
-- Keep accepted records and scoped keys for the promised retry window; there
-- is no automatic retention, dispatch, retry, or replay in this phase.
CREATE TABLE IF NOT EXISTS event_deliveries (
    delivery_id UUID PRIMARY KEY,
    source TEXT NOT NULL CHECK (length(btrim(source)) BETWEEN 1 AND 256),
    operation TEXT NOT NULL CHECK (length(btrim(operation)) BETWEEN 1 AND 256),
    idempotency_key TEXT NOT NULL CHECK (length(btrim(idempotency_key)) BETWEEN 1 AND 256),
    event_id TEXT NOT NULL CHECK (length(btrim(event_id)) BETWEEN 1 AND 256),
    event_type TEXT NOT NULL CHECK (length(btrim(event_type)) BETWEEN 1 AND 256),
    -- JSON preserves canonical numeric spelling for repeatable admission hashes.
    payload JSON NOT NULL CHECK (json_typeof(payload) = 'object')
        CHECK (octet_length(payload::text) <= 262144),
    payload_hash TEXT NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    trace_id TEXT CHECK (length(btrim(trace_id)) BETWEEN 1 AND 256),
    parent_id TEXT CHECK (length(btrim(parent_id)) BETWEEN 1 AND 256),
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state = 'pending'),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count = 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, operation, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_event_deliveries_created_at
    ON event_deliveries (created_at, delivery_id);

-- Preserve admission rows while evolving the original restrictions. This DO
-- statement is atomic, including constraint replacement; validation failure
-- rolls back all its changes. Apply during a maintenance window: ALTER TABLE
-- requires an exclusive lock. The bounded lock wait fails explicitly.
DO $$
BEGIN
    PERFORM set_config('lock_timeout', '5s', true);
    PERFORM pg_advisory_xact_lock(734832002);
    ALTER TABLE event_deliveries
        ADD COLUMN IF NOT EXISTS worker_id TEXT,
        ADD COLUMN IF NOT EXISTS lease_token UUID,
        ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS available_at TIMESTAMPTZ NOT NULL DEFAULT now();
    ALTER TABLE event_deliveries
        DROP CONSTRAINT IF EXISTS event_deliveries_state_check,
        DROP CONSTRAINT IF EXISTS event_deliveries_attempt_count_check,
        DROP CONSTRAINT IF EXISTS event_deliveries_lease_check;
    ALTER TABLE event_deliveries
        ADD CONSTRAINT event_deliveries_state_check CHECK
            (state IN ('pending','processing','retry_scheduled','completed','dead_lettered')),
        ADD CONSTRAINT event_deliveries_attempt_count_check CHECK
            (attempt_count >= 0 AND (state NOT IN ('processing','completed') OR attempt_count > 0)),
        ADD CONSTRAINT event_deliveries_lease_check CHECK (
            (state = 'processing' AND worker_id IS NOT NULL
             AND length(btrim(worker_id)) BETWEEN 1 AND 256
             AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)
            OR (state <> 'processing' AND worker_id IS NULL
                AND lease_token IS NULL AND lease_expires_at IS NULL));
END $$;

CREATE INDEX IF NOT EXISTS idx_event_deliveries_eligible
    ON event_deliveries (available_at, created_at, delivery_id)
    WHERE state IN ('pending', 'retry_scheduled');
CREATE INDEX IF NOT EXISTS idx_event_deliveries_expired
    ON event_deliveries (lease_expires_at) WHERE state = 'processing';
CREATE UNIQUE INDEX IF NOT EXISTS idx_event_deliveries_lease_token
    ON event_deliveries (lease_token) WHERE lease_token IS NOT NULL;

-- Permitted store transitions: due pending/retry_scheduled -> processing;
-- expired processing -> processing with NEW token and incremented attempt;
-- unexpired processing -> completed with matching worker/token, clearing lease.
-- No operation schedules retries or dead-letters work yet. Processing happens
-- outside claim transactions; tokens fence storage updates, not external effects.

-- Muninn memory records (MemoryRecord).
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    namespace TEXT NOT NULL DEFAULT 'default',
    content TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    trace_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories (namespace);
CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_memories_trace_id ON memories (trace_id);

-- Full system event log (Event / EventBus.SystemLogStore). This is what
-- GET /events reads to feed the Decision Graph, Reasoning Intelligence, and
-- Learning Loop dashboard panels — column shape must be enough to
-- reconstruct the existing Event dataclass exactly (id, event_type, payload,
-- created_at); trace_id is additive and not part of that reconstruction.
CREATE TABLE IF NOT EXISTS system_events (
    id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    trace_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_system_events_event_type ON system_events (event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_created_at ON system_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_events_trace_id ON system_events (trace_id);

-- Outcome records (Outcome). Primary key is a row id, NOT event_id —
-- event_id is a plain indexed column (per corrected schema).
CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY,
    event_id UUID NOT NULL,
    trace_id UUID,
    initial_state TEXT NOT NULL,
    chosen_path TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('success', 'failure', 'partial')),
    execution_time DOUBLE PRECISION NOT NULL,
    error_logs JSONB NOT NULL DEFAULT '[]'::jsonb,
    user_feedback TEXT,
    performance_score DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outcomes_event_id ON outcomes (event_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_trace_id ON outcomes (trace_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_chosen_path ON outcomes (chosen_path);

-- Authoritative learned path weights. Replaces the old indirection where
-- weights were reconstructed by searching Muninn memory records.
CREATE TABLE IF NOT EXISTS learned_weights (
    path TEXT PRIMARY KEY,
    weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reasoning patterns (Pattern). outcomes stays JSONB, matching the existing
-- Pattern.outcomes: list[dict] shape exactly — not normalized into a sixth
-- table, per the approved design.
CREATE TABLE IF NOT EXISTS reasoning_patterns (
    pattern_id UUID PRIMARY KEY,
    context_signature JSONB NOT NULL,
    preferred_path_distribution JSONB NOT NULL,
    success_rate DOUBLE PRECISION NOT NULL,
    conditions JSONB NOT NULL,
    matched_contexts INT NOT NULL DEFAULT 1,
    outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
