# Changelog

All notable changes to HUGINN // MUNINN will be documented in this file.

The format is based on Keep a Changelog. Versioning can be introduced when release tags begin.

## [Unreleased]

### Phase 3 Engineering Checkpoints

The following local milestones are prepared for synchronization, not a production release. Earlier changelog entries are retained below as historical scaffold work.

- `6c52e25` - Strengthened JSON security graph persistence with fsynced directory replacement, persisted evidence precedence, caller-driven resubmission/restart recovery coverage, and updated demonstrations. This does not implement automatic event replay.
- `59a8684` - Synchronized repository module loading across evidence, Wazuh, and GuardDuty adapters; restored module identities under a shared lock; added concurrency regression coverage and the frontend ESLint configuration.
- `3d69056` - Hardened EventBus lifecycle/admission, contained storage and handler failures, added configurable processing/shutdown budgets, sanitized counters, and HTTP 503 for unavailable submissions. Delivery remains best-effort in-memory.
- `1b945db` - Added separate PostgreSQL durable admission, validated recoverable envelopes, database-enforced scoped idempotency, typed errors, and isolated rollback/fresh-process retrieval tests.
- `9371666` - Added atomic claims, database-time leases, ownership-checked completion, explicit expired-lease recovery, and compatible delivery-schema evolution. No production workflow dispatcher is enabled.

### Documentation and Validation

- Updated the overview, implemented architecture, persistence boundaries, schema precautions, isolated test instructions, and local-only security limitations.
- Recorded Phase 2 validation on 2026-10-27: 278 backend tests discovered; 274 passed with isolated PostgreSQL databases and four report-writing tests passed separately in a temporary copy. All 278 passed across isolated runs, not one combined invocation.
- Recorded 41 focused delivery tests, a temporary worker-crash recovery diagnostic, Ruff, frontend lint, TypeScript validation, and production build passing. These validations were not rerun during the documentation phase.
- Automatic durable dispatch, retry/dead-letter execution policies, lease renewal, complete side-effect deduplication, and end-to-end/exactly-once external execution guarantees remain unsupported. Production deployment is not approved.

### Added

- FastAPI backend with health, chat, memory, event, and security analysis endpoints.
- Next.js dashboard for command submission, event visibility, graph decisions, learning outcomes, and reasoning patterns.
- In-memory event bus with asynchronous processing and system logs fallback.
- Adaptive intelligence graph with dynamic branch routing.
- Decision engine with learned path weights.
- Outcome tracking and closed-loop learning events.
- Reasoning pattern abstraction with context signatures, similarity matching, and pattern influence.
- Docker Compose services for PostgreSQL and ChromaDB.
- GitHub private-repository documentation, MIT license, repository tree, and release checklist.
- SOC portfolio structure: `core/`, `labs/`, `detection-engine/`, `playbooks/`, `reports/`, `evidence/`, `templates/`, and `scripts/`.
- Windows authentication brute-force lab with MITRE ATT&CK mapping.
- Wazuh and Suricata detection rule examples.
- SOC analyst templates for labs, detection rules, and incident reports.
- Wazuh XML validation script.

### Security

- Added repository hygiene guidance and ignored local runtime artifacts.
