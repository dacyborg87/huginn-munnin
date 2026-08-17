"""Storage Protocols and backend implementations for the Muninn Persistence Foundation.

Four independent storage concerns, each with an in-memory backend (default,
used by the existing fast test suite) and a Postgres backend:

- MemoryStore       (Muninn memory records)
- OutcomeStore       (outcome history + authoritative learned path weights)
- SystemLogStore     (full event log — feeds GET /events)
- PatternStore       (reasoning patterns)

Reasoning components depend on these Protocols, never on asyncpg directly.
"""
