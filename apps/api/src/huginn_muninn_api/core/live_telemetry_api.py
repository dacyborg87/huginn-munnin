"""Read-only API helpers for live telemetry dashboard summaries."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any


SEVERITY_ORDER = ["critical", "high", "medium", "low", "informational"]


class LiveTelemetryApi:
    """Build dashboard-ready telemetry summaries from existing JSON reports."""

    def __init__(self, repository_root: Path | str) -> None:
        self.repository_root = Path(repository_root)

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
        path = self.repository_root / "reports" / "real-data-pipeline-output.json"
        return self._read_json(path, default={"evidence_records": []})

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
