import asyncio
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import core

# Legacy artifact tests temporarily select the repository-root core package.
# Resolve these API-only modules without leaving that package's search path changed.
with patch.object(core, "__path__", [str(Path(__file__).parents[1] / "src/core"), *core.__path__]):
    from core.event_delivery import DeliveryEnvelope, DeliveryStorageError, DeliveryValidationError
    from core.stores.event_delivery_store import PostgresDeliveryStore


def envelope(**changes):
    return replace(
        DeliveryEnvelope("synthetic", "test", "key", "source-id", "TEST", {"a": 1}), **changes
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {1: "bad"},
        {"a": float("nan")},
        {"a": float("inf")},
        {"a": object()},
        {"a": (1, 2)},
        {"a": "\x00"},
        {"a": "\ud800"},
    ],
)
def test_invalid_payload(payload):
    with pytest.raises(DeliveryValidationError):
        envelope(payload=payload).encode()


@pytest.mark.parametrize(
    "changes",
    [
        {"source": ""},
        {"operation": " "},
        {"idempotency_key": "x" * 257},
        {"event_id": None},
        {"schema_version": True},
        {"schema_version": 2},
        {"trace_id": ""},
        {"parent_id": 12},
    ],
)
def test_invalid_envelope(changes):
    with pytest.raises(DeliveryValidationError):
        envelope(**changes).encode()


def test_payload_encoding_and_size():
    assert (
        envelope(payload={"a": 1, "b": [2]}).encode()
        == envelope(payload={"b": [2], "a": 1}).encode()
    )
    with pytest.raises(DeliveryValidationError):
        envelope(payload={"a": "x" * 262144}).encode()
    cyclic = {}
    cyclic["cycle"] = cyclic
    with pytest.raises(DeliveryValidationError):
        envelope(payload=cyclic).encode()


def test_validation_precedes_database_access():
    pool = MagicMock()
    with pytest.raises(DeliveryValidationError):
        asyncio.run(PostgresDeliveryStore(pool).admit(envelope(payload={"a": object()})))
    pool.acquire.assert_not_called()


def test_connection_failure_is_explicit_and_sanitized():
    pool = MagicMock()
    pool.acquire.side_effect = ConnectionRefusedError("SECRET_PASSWORD")
    original = envelope()
    with pytest.raises(DeliveryStorageError) as error:
        asyncio.run(PostgresDeliveryStore(pool).admit(original))
    assert "SECRET_PASSWORD" not in str(error.value)
    assert original.idempotency_key == "key"
    assert original.payload == {"a": 1}
