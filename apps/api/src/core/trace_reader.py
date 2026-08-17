"""Phase A2: standalone, read-only trace reconstruction.

Gathers whatever memories/events/outcomes/patterns/weights are associated
with a `trace_id` from the existing stores. Not wired into the live request
pipeline this milestone — Orchestrator is untouched. Deliberately kept out
of `huginn_muninn_api.core` (which owns app wiring like `persistence.py`)
so this stays a plain `core/` read path with no dependency on anything
forbidden to modify.

Missing components are not errors: an unknown trace_id, or a trace with
only some of its pieces present, simply yields empty lists for the rest.
"""

from __future__ import annotations

from core.reasoning_types import Pattern
from core.stores.memory_store import MemoryStore
from core.stores.outcome_store import OutcomeStore
from core.stores.pattern_store import PatternStore
from core.stores.system_log_store import SystemLogStore
from core.trace_context import TraceContext


async def reconstruct_trace(
    trace_id: str,
    *,
    memory_store: MemoryStore,
    outcome_store: OutcomeStore,
    system_log_store: SystemLogStore,
    pattern_store: PatternStore | None = None,
) -> TraceContext:
    """Read-only. `pattern_store` is optional — omitting it simply leaves
    `related_patterns` empty; pattern correlation is never a precondition
    for the rest of the trace to reconstruct."""
    events = await system_log_store.find_by_trace_id(trace_id)
    memories = await memory_store.find_by_trace_id(trace_id)
    outcomes = await outcome_store.find_by_trace_id(trace_id)
    current_learned_weights = await outcome_store.get_weights()

    related_patterns: list[Pattern] = []
    if pattern_store is not None and outcomes:
        related_patterns = await _find_related_patterns(pattern_store, outcomes)

    return TraceContext(
        trace_id=trace_id,
        events=events,
        memories=memories,
        outcomes=outcomes,
        related_patterns=related_patterns,
        current_learned_weights=current_learned_weights,
    )


async def _find_related_patterns(pattern_store: PatternStore, outcomes: list) -> list[Pattern]:
    """O(N) scan over the full pattern set — acceptable at today's scale
    (a handful of patterns). No index exists for this and none is added;
    Pattern.outcomes stays JSONB, per the approved design."""
    outcome_event_ids = {outcome.event_id for outcome in outcomes}
    all_patterns = await pattern_store.load()

    matches: list[Pattern] = []
    for pattern in all_patterns.values():
        pattern_event_ids = {
            str(entry.get("event_id"))
            for entry in pattern.outcomes
            if isinstance(entry, dict) and entry.get("event_id")
        }
        if pattern_event_ids & outcome_event_ids:
            matches.append(pattern)
    return matches
