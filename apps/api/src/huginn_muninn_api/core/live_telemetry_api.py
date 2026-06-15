"""Read-only API helpers for live telemetry dashboard summaries."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
from typing import Any


SEVERITY_ORDER = ["critical", "high", "medium", "low", "informational"]
LOGGER = logging.getLogger(__name__)


class LiveTelemetryApi:
    """Build dashboard-ready telemetry summaries from existing JSON reports."""

    def __init__(
        self,
        repository_root: Path | str,
        poll_interval: float = 30.0,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.repository_root = Path(repository_root)
        self.poll_interval = poll_interval
        self._clock = clock or (lambda: datetime.now(UTC).isoformat())
        self.pipeline_report_path = (
            self.repository_root / "reports" / "real-data-pipeline-output.json"
        )
        self._pipeline_cache: dict[str, Any] = {"evidence_records": []}
        self._last_successful_reload: str | None = None
        self._last_reload_error: str | None = None
        self._poll_task: asyncio.Task[None] | None = None

    async def start_polling(self) -> None:
        """Start background report polling and load the first snapshot."""

        self.reload_pipeline_report()
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop_polling(self) -> None:
        """Stop the background report polling task."""

        if self._poll_task is None:
            return
        self._poll_task.cancel()
        try:
            await self._poll_task
        except asyncio.CancelledError:
            pass
        self._poll_task = None

    def last_updated(self) -> dict[str, Any]:
        return {
            "entity_searched": "live_telemetry_report",
            "last_successful_reload": self._last_successful_reload,
            "last_reload_error": self._last_reload_error,
            "poll_interval_seconds": self.poll_interval,
            "source_path": str(self.pipeline_report_path),
            "cache_status": self._cache_status(),
            "explanation": (
                "This timestamp records the last successful reload of the Wazuh "
                "pipeline report used by the dashboard telemetry API."
            ),
        }

    def summary(self) -> dict[str, Any]:
        events = self.events()["events"]
        return {
            "entity_searched": "live_telemetry",
            "recent_events": events,
            "severity_breakdown": self.severity_breakdown(events),
            "top_rules": self.rules()["rules"],
            "top_agents": self.agents()["agents"],
            "evidence": self.evidence(),
            "explanation": (
                "This summarizes the current Wazuh pipeline output, evidence "
                "records, and graph events for dashboard visibility."
            ),
        }

    def events(self, limit: int = 20) -> dict[str, Any]:
        records = self._pipeline_payload().get("evidence_records", [])
        events = [self._event_from_evidence(record) for record in records]
        events.extend(self._graph_events())
        sorted_events = sorted(
            events,
            key=lambda event: event.get("timestamp") or "",
            reverse=True,
        )
        return {
            "entity_searched": "security_events",
            "events": sorted_events[:limit],
            "count": min(len(sorted_events), limit),
            "total_available": len(sorted_events),
            "explanation": (
                "These are the newest security events Huginn can derive from "
                "pipeline evidence records and graph event nodes."
            ),
        }

    def rules(self, limit: int = 10) -> dict[str, Any]:
        events = self.events(limit=200)["events"]
        counter: Counter[tuple[str, str]] = Counter()
        for event in events:
            rule_id = event["rule_id"] or "unknown"
            description = event["description"] or "No description available"
            counter[(rule_id, description)] += 1
        rules = [
            {
                "rule_id": rule_id,
                "description": description,
                "occurrence_count": count,
            }
            for (rule_id, description), count in counter.most_common(limit)
        ]
        return {
            "entity_searched": "rule_ids",
            "rules": rules,
            "explanation": "These are the most common rule IDs in current telemetry.",
        }

    def agents(self, limit: int = 10) -> dict[str, Any]:
        events = self.events(limit=200)["events"]
        counter = Counter(event["source_agent"] or "unknown" for event in events)
        agents = [
            {"agent_name": agent, "event_count": count}
            for agent, count in counter.most_common(limit)
        ]
        return {
            "entity_searched": "agents",
            "agents": agents,
            "explanation": "These are the agents or sources producing the most events.",
        }

    def evidence(self) -> dict[str, Any]:
        records = self._pipeline_payload().get("evidence_records", [])
        confidence_counts = Counter(
            str(record.get("confidence", {}).get("level", "unknown")).lower()
            for record in records
        )
        gaps = [self._evidence_gap(record) for record in records if self._has_gap(record)]
        return {
            "entity_searched": "dashboard_evidence",
            "summary": {
                "total_evidence_records": len(records),
                "high_confidence": confidence_counts.get("high", 0),
                "medium_confidence": confidence_counts.get("medium", 0),
                "low_confidence": confidence_counts.get("low", 0),
                "evidence_gaps": len(gaps),
            },
            "evidence_records": records,
            "evidence_gaps": gaps,
            "explanation": (
                "This shows evidence volume, confidence distribution, and "
                "records that need more context."
            ),
        }

    def severity_breakdown(self, events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        source_events = events if events is not None else self.events(limit=200)["events"]
        counter = Counter(self._normalize_severity(event.get("severity")) for event in source_events)
        total = sum(counter.values())
        return [
            {
                "severity": severity,
                "count": counter.get(severity, 0),
                "percentage": round((counter.get(severity, 0) / total) * 100, 1)
                if total
                else 0.0,
            }
            for severity in SEVERITY_ORDER
        ]

    def _pipeline_payload(self) -> dict[str, Any]:
        if self._last_successful_reload is None:
            self.reload_pipeline_report()
        return self._pipeline_cache

    def reload_pipeline_report(self) -> bool:
        """Reload the Wazuh pipeline report, preserving the last good cache on failure."""

        try:
            payload = json.loads(self.pipeline_report_path.read_text(encoding="utf-8"))
        except OSError as error:
            self._last_reload_error = str(error)
            LOGGER.warning(
                "Unable to reload live telemetry report from %s: %s",
                self.pipeline_report_path,
                error,
            )
            return False
        except json.JSONDecodeError as error:
            self._last_reload_error = str(error)
            LOGGER.warning(
                "Malformed live telemetry report at %s: %s",
                self.pipeline_report_path,
                error,
            )
            return False

        if not isinstance(payload, dict):
            self._last_reload_error = "expected JSON object"
            LOGGER.warning(
                "Malformed live telemetry report at %s: expected JSON object",
                self.pipeline_report_path,
            )
            return False

        self._pipeline_cache = payload
        self._last_successful_reload = self._clock()
        self._last_reload_error = None
        return True

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval)
            self.reload_pipeline_report()

    def _cache_status(self) -> str:
        records = self._pipeline_cache.get("evidence_records", [])
        if self._last_successful_reload is None:
            return "empty"
        if self._last_reload_error:
            return "stale"
        return "ready" if records else "ready_empty"

    def _graph_events(self) -> list[dict[str, Any]]:
        path = self.repository_root / "reports" / "knowledge-graph.json"
        graph = self._read_json(path, default={"nodes": []})
        events = []
        for node in graph.get("nodes", []):
            if node.get("type") != "Event":
                continue
            properties = node.get("properties", {})
            context = properties.get("normalized_context", {})
            events.append(
                {
                    "event_id": node.get("id"),
                    "timestamp": properties.get("timestamp"),
                    "rule_id": context.get("detection_name") or node.get("label"),
                    "description": node.get("label") or "Graph event",
                    "severity": self._normalize_severity(properties.get("severity")),
                    "source_agent": (
                        context.get("target_host")
                        or context.get("host")
                        or properties.get("source_system")
                        or "unknown"
                    ),
                    "source": "knowledge_graph",
                }
            )
        return events

    def _event_from_evidence(self, record: dict[str, Any]) -> dict[str, Any]:
        summary = str(record.get("summary", ""))
        title = str(record.get("title", ""))
        confidence = record.get("confidence", {})
        return {
            "event_id": record.get("source_reference"),
            "timestamp": record.get("timestamp"),
            "rule_id": self._extract_rule_id(summary),
            "description": self._description_from_title(title),
            "severity": self._extract_severity(summary, confidence),
            "source_agent": self._extract_host(summary),
            "source": "wazuh_pipeline",
            "evidence_id": record.get("evidence_id"),
        }

    def _evidence_gap(self, record: dict[str, Any]) -> dict[str, Any]:
        related = record.get("related_entities", {})
        confidence = record.get("confidence", {})
        reasons = []
        if not related.get("mitre_techniques"):
            reasons.append("MITRE technique missing")
        if str(confidence.get("level", "")).lower() == "low":
            reasons.append("Confidence low")
        if not related.get("defense_recommendations"):
            reasons.append("Recommendation missing")
        return {
            "evidence_id": record.get("evidence_id"),
            "title": record.get("title"),
            "reasons": reasons,
            "explanation": (
                f"{record.get('title', 'This evidence record')} needs analyst review "
                f"because: {', '.join(reasons)}."
            ),
        }

    def _has_gap(self, record: dict[str, Any]) -> bool:
        related = record.get("related_entities", {})
        confidence = record.get("confidence", {})
        return (
            not related.get("mitre_techniques")
            or str(confidence.get("level", "")).lower() == "low"
            or not related.get("defense_recommendations")
        )

    @staticmethod
    def _extract_rule_id(summary: str) -> str:
        match = re.search(r"rule\s+([A-Za-z0-9_.:-]+)", summary)
        return match.group(1) if match else "unknown"

    @staticmethod
    def _extract_host(summary: str) -> str:
        match = re.search(r"host\s+([A-Za-z0-9_.:-]+)", summary)
        return match.group(1) if match else "unknown"

    def _extract_severity(self, summary: str, confidence: dict[str, Any]) -> str:
        match = re.search(r"severity\s+([A-Za-z]+)", summary)
        if match:
            return self._normalize_severity(match.group(1))
        return self._normalize_severity(confidence.get("level"))

    @staticmethod
    def _description_from_title(title: str) -> str:
        if ":" not in title:
            return title or "No description available"
        return title.split(":", 1)[1].strip() or title

    @staticmethod
    def _normalize_severity(value: Any) -> str:
        severity = str(value or "informational").lower()
        if severity in {"info", "informative", "unknown"}:
            return "informational"
        if severity not in SEVERITY_ORDER:
            return "informational"
        return severity

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
