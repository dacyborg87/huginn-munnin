"""Pure data representation of a reconstructed trace.

A trace is everything the existing stores can produce for one `trace_id` —
nothing here is computed or fabricated; every field is either a direct
lookup or, for `related_patterns`, an explicit best-effort correlation
(see `core/trace_reader.py`). No schema change backs this: `trace_id` was
already a column on `memories`, `system_events`, and `outcomes` as of the
persistence milestone (f424178).
"""

from dataclasses import dataclass, field

from core.events import Event
from core.outcomes import Outcome
from core.reasoning_types import Pattern
from huginn_muninn_api.schemas.memory import MemoryRecord


@dataclass
class TraceContext:
    trace_id: str
    events: list[Event] = field(default_factory=list)
    memories: list[MemoryRecord] = field(default_factory=list)
    outcomes: list[Outcome] = field(default_factory=list)

    # Best-effort only: a pattern is included if any of its recorded
    # outcomes' event_id matches an event_id found in `outcomes` above.
    # Outcome itself carries no trace_id field, so this is an O(N) scan
    # over the pattern set, not an indexed lookup — never a required
    # condition for a trace to reconstruct successfully.
    related_patterns: list[Pattern] = field(default_factory=list)

    # CURRENT global learned-path weights at reconstruction time — NOT a
    # historical snapshot of what the weights were *during* this trace.
    # No weight history/versioning exists in the schema; fabricating a
    # point-in-time value would be misleading, so this is deliberately
    # labeled as current state only.
    current_learned_weights: dict[str, float] = field(default_factory=dict)
