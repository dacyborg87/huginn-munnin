"""Trace-id extraction helper.

trace_id is a correlation id only — it links records produced during the
same reasoning/execution flow. It is derived from data the orchestrator
already threads through every event payload and memory-record metadata
(``command_event_id``); no existing payload shape, MemoryRecord field, or
EventType is changed to support it.
"""

from __future__ import annotations

import uuid
from typing import Any


def extract_trace_id(value: Any) -> uuid.UUID | None:
    """Best-effort parse of a correlation id into a UUID for storage.

    Returns None if the value is missing or not a valid UUID string —
    trace_id is always optional, never required for a write to succeed.
    """
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def trace_id_from_metadata(metadata: dict[str, Any] | None) -> uuid.UUID | None:
    if not isinstance(metadata, dict):
        return None
    return extract_trace_id(metadata.get("command_event_id"))


def trace_id_from_event_payload(payload: dict[str, Any], event_id: str) -> uuid.UUID | None:
    """Every event carries its own thread's correlation id in
    ``payload["command_event_id"]`` — except the USER_COMMAND_RECEIVED event
    itself, which *is* that command and has no such key, so its own id is
    the trace root.
    """
    if isinstance(payload, dict) and payload.get("command_event_id"):
        return extract_trace_id(payload["command_event_id"])
    return extract_trace_id(event_id)
