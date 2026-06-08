"""Parse raw Wazuh alert dictionaries into normalized event records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventRecord:
    """Small normalized event shape for Phase 1A real-data ingestion."""

    id: str | None
    timestamp: str | None
    source: str
    rule_id: str | None
    description: str | None
    host: str | None
    mitre_techniques: list[str]
    severity: str | None


def parse_wazuh_alert(alert: dict[str, Any]) -> EventRecord:
    """Convert one raw Wazuh alert dictionary into an EventRecord."""

    rule = _dict_or_empty(alert.get("rule"))
    agent = _dict_or_empty(alert.get("agent"))
    mitre = _dict_or_empty(rule.get("mitre"))

    return EventRecord(
        id=_optional_string(alert.get("id")),
        timestamp=_optional_string(alert.get("timestamp")),
        source="wazuh",
        rule_id=_optional_string(rule.get("id")),
        description=_optional_string(rule.get("description")),
        host=_optional_string(agent.get("name")),
        mitre_techniques=_mitre_techniques(mitre.get("id")),
        severity=_severity(rule.get("level")),
    )


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _mitre_techniques(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _severity(level: Any) -> str | None:
    if level is None:
        return None
    try:
        numeric_level = int(level)
    except (TypeError, ValueError):
        return str(level)

    if numeric_level >= 12:
        return "critical"
    if numeric_level >= 7:
        return "high"
    if numeric_level >= 4:
        return "medium"
    return "low"

