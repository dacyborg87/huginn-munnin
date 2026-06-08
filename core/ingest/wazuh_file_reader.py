"""Read Wazuh alert JSON files and normalize valid records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.ingest.wazuh_parser import EventRecord, parse_wazuh_alert


@dataclass(frozen=True)
class WazuhFileReadResult:
    """Normalized events and read statistics for one Wazuh alert file."""

    events: list[EventRecord]
    summary: dict[str, int | str]


def read_wazuh_alert_file(path: Path | str) -> WazuhFileReadResult:
    """Read one Wazuh JSON alert file and return normalized EventRecord objects."""

    input_path = Path(path)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return WazuhFileReadResult(
            events=[],
            summary={
                "records_read": 0,
                "records_parsed": 0,
                "records_skipped": 1,
                "source_path": str(input_path),
                "error": str(error),
            },
        )

    records = _records_from_payload(payload)
    events: list[EventRecord] = []
    skipped = 0

    for record in records:
        if not isinstance(record, dict):
            skipped += 1
            continue
        try:
            events.append(parse_wazuh_alert(record))
        except (TypeError, ValueError):
            skipped += 1

    return WazuhFileReadResult(
        events=events,
        summary={
            "records_read": len(records),
            "records_parsed": len(events),
            "records_skipped": skipped,
            "source_path": str(input_path),
        },
    )


def _records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    return [payload]
