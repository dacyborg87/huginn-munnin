"""SOC event bus for routing detections, lab events, playbooks, and reports."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.detection_response_map import resolve_playbook_route
from core.event_schema import (
    EventSeverity,
    EventSource,
    MitreMapping,
    SocEvent,
    SocEventType,
    normalize_mitre_mapping,
)

EventHandler = Callable[[SocEvent], None]


class SocEventBus:
    """In-memory SOC event bus with JSONL persistence for analyst review."""

    def __init__(self, repository_root: Path | str = ".") -> None:
        self.repository_root = Path(repository_root)
        self._queue: deque[SocEvent] = deque()
        self._subscribers: dict[SocEventType, list[EventHandler]] = defaultdict(list)
        self.event_log_path = self.repository_root / "reports" / "soc-events.jsonl"

    def subscribe(self, event_type: SocEventType, handler: EventHandler) -> None:
        self._subscribers[event_type].append(handler)

    def emit(self, event: SocEvent) -> str:
        self._queue.append(event)
        self._persist_event(event)
        return event.event_id

    def process_pending(self) -> list[SocEvent]:
        processed: list[SocEvent] = []
        while self._queue:
            event = self._queue.popleft()
            for handler in self._subscribers.get(event.event_type, []):
                handler(event)
            processed.append(event)
        return processed

    def load_event_history(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.event_log_path)

    def load_detection_outcomes(self) -> list[dict[str, Any]]:
        return self._read_jsonl(self.repository_root / "reports" / "detection-outcomes.jsonl")

    def ingest_detection_alert(
        self,
        source_system: EventSource | str,
        raw_payload: dict[str, Any],
        *,
        detection_name: str = "",
        mitre_mapping: list[MitreMapping] | list[dict[str, str]] | dict[str, str] | None = None,
        severity: EventSeverity | str = EventSeverity.MEDIUM,
        normalized_context: dict[str, Any] | None = None,
    ) -> str:
        context = dict(normalized_context or {})
        if detection_name:
            context["detection_name"] = detection_name

        event = SocEvent(
            event_type=SocEventType.DETECTION_ALERT,
            source_system=source_system,
            mitre_mapping=normalize_mitre_mapping(mitre_mapping),
            severity=severity,
            raw_payload=raw_payload,
            normalized_context=context,
        )
        event_id = self.emit(event)
        self._emit_route_for_detection(event)
        return event_id

    def ingest_lab_event(
        self,
        raw_payload: dict[str, Any],
        *,
        lab_id: str,
        attack_step: str,
        mitre_mapping: list[MitreMapping] | list[dict[str, str]] | dict[str, str] | None = None,
        severity: EventSeverity | str = EventSeverity.INFO,
    ) -> str:
        event = SocEvent(
            event_type=SocEventType.LAB_EVENT,
            source_system=EventSource.LAB,
            mitre_mapping=normalize_mitre_mapping(mitre_mapping),
            severity=severity,
            raw_payload=raw_payload,
            normalized_context={"lab_id": lab_id, "attack_step": attack_step},
        )
        return self.emit(event)

    def _emit_route_for_detection(self, event: SocEvent) -> None:
        route = resolve_playbook_route(event)
        route_event = SocEvent(
            event_type=SocEventType.PLAYBOOK_SELECTED,
            source_system=EventSource.HUGINN,
            mitre_mapping=event.mitre_mapping,
            severity=event.severity,
            raw_payload={"source_event_id": event.event_id},
            normalized_context={
                "route_id": route.route_id,
                "playbook_path": route.playbook_path,
                "reason": route.reason,
                "priority": route.priority,
                "source_detection": event.normalized_context.get("detection_name", ""),
            },
        )
        self.emit(route_event)

    def _persist_event(self, event: SocEvent) -> None:
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.event_log_path.open("a", encoding="utf-8") as event_log:
            event_log.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records
