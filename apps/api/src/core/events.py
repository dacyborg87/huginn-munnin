"""Event and EventType definitions.

Split out of event_bus.py so core/stores/system_log_store.py can depend on
these types without a circular import (event_bus.py in turn depends on the
store implementations). No values or shapes changed — this is a pure
relocation of the existing EventType enum and Event dataclass.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class EventType(StrEnum):
    USER_COMMAND_RECEIVED = "USER_COMMAND_RECEIVED"
    CONTEXT_SIGNATURE_CREATED = "CONTEXT_SIGNATURE_CREATED"
    PATTERN_MATCH_LOOKUP = "PATTERN_MATCH_LOOKUP"
    AI_CONTEXT_ENRICHED = "AI_CONTEXT_ENRICHED"
    AI_THINKING_STARTED = "AI_THINKING_STARTED"
    AI_DECISION_MADE = "AI_DECISION_MADE"
    AI_PLAN_CREATED = "AI_PLAN_CREATED"
    AI_TASK_EXECUTING = "AI_TASK_EXECUTING"
    AI_TASK_COMPLETED = "AI_TASK_COMPLETED"
    AI_OUTCOME_RECORDED = "AI_OUTCOME_RECORDED"
    AI_PATTERN_RECORDED = "AI_PATTERN_RECORDED"
    MEMORY_WRITTEN = "MEMORY_WRITTEN"
    AGENT_STATUS_UPDATED = "AGENT_STATUS_UPDATED"


@dataclass(frozen=True)
class Event:
    event_type: EventType
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
