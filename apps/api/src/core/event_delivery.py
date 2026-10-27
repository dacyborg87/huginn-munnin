"""Version-one durable admission envelopes; independent of EventBus dispatch."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

MAX_PAYLOAD_BYTES = 262_144


class DeliveryValidationError(ValueError):
    """The envelope cannot be admitted."""


class DeliveryConflict(ValueError):
    """The scoped key already identifies a different envelope."""


class DeliveryOwnershipError(RuntimeError):
    """Completion rejected: ownership is absent, replaced, or expired."""


class DeliveryStorageError(RuntimeError):
    """Admission was not confirmed; retry the same envelope and key."""


def _json_value(value: Any) -> None:
    if type(value) is str and "\x00" in value:
        raise DeliveryValidationError("Payload cannot contain NUL characters")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for key in value:
            _json_value(key)
        for item in value.values():
            _json_value(item)
        return
    raise DeliveryValidationError("Payload must contain only finite JSON values")


@dataclass(frozen=True)
class DeliveryEnvelope:
    source: str
    operation: str
    idempotency_key: str
    event_id: str
    event_type: str
    payload: dict[str, Any]
    schema_version: int = 1
    trace_id: str | None = None
    parent_id: str | None = None

    def encode(self) -> tuple[str, str]:
        for value in (
            self.source,
            self.operation,
            self.idempotency_key,
            self.event_id,
            self.event_type,
        ):
            if type(value) is not str or not value.strip() or len(value) > 256 or "\x00" in value:
                raise DeliveryValidationError(
                    "Identifiers must be nonempty strings up to 256 characters"
                )
        for value in (self.trace_id, self.parent_id):
            if value is not None and (
                type(value) is not str or not value.strip() or len(value) > 256 or "\x00" in value
            ):
                raise DeliveryValidationError("Invalid optional identifier")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise DeliveryValidationError("Only envelope schema version 1 is supported")
        if type(self.payload) is not dict:
            raise DeliveryValidationError("Payload must be a JSON object")
        try:
            _json_value(self.payload)
            payload = json.dumps(
                self.payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            encoded = payload.encode("utf-8")
            for value in (
                self.source,
                self.operation,
                self.idempotency_key,
                self.event_id,
                self.event_type,
                self.trace_id,
                self.parent_id,
            ):
                if value is not None:
                    value.encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise DeliveryValidationError("Envelope is not valid UTF-8 JSON") from None
        if len(encoded) > MAX_PAYLOAD_BYTES:
            raise DeliveryValidationError("Payload exceeds 262144 UTF-8 bytes")
        return payload, hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class DeliveryRecord:
    delivery_id: UUID
    envelope: DeliveryEnvelope
    payload_hash: str
    state: str
    attempt_count: int
    created_at: datetime
    updated_at: datetime
    worker_id: str | None = None
    lease_token: UUID | None = None
    lease_expires_at: datetime | None = None
    available_at: datetime | None = None
