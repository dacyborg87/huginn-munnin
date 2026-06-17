"""Runtime API adapter for Wazuh alert ingestion."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable
import types


class WazuhIngestApi:
    """Parse Wazuh alerts and publish the existing live telemetry report format."""

    def __init__(
        self,
        repository_root: Path | str,
        parser: Callable[[dict[str, Any]], Any] | None = None,
        graph_ingestor: Callable[[list[Any], Any], tuple[Any, dict[str, int]]] | None = None,
        evidence_builder: Callable[..., list[Any]] | None = None,
        graph_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.output_path = self.repository_root / "reports" / "real-data-pipeline-output.json"
        self._parser = parser
        self._graph_ingestor = graph_ingestor
        self._evidence_builder = evidence_builder
        self._graph_factory = graph_factory

    def ingest(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        """Ingest one Wazuh alert or a list of alerts."""

        alerts = self._alerts_from_payload(payload)
        modules = self._repository_modules()
        parse_wazuh_alert = self._parser or modules["parse_wazuh_alert"]
        ingest_event_records = self._graph_ingestor or modules["ingest_event_records"]
        build_real_data_evidence = self._evidence_builder or modules["build_real_data_evidence"]
        graph = (self._graph_factory or modules["KnowledgeGraph"])()

        events = []
        records_skipped = 0
        for alert in alerts:
            if not isinstance(alert, dict):
                records_skipped += 1
                continue
            if not self._has_required_fields(alert):
                records_skipped += 1
                continue
            try:
                events.append(parse_wazuh_alert(alert))
            except (TypeError, ValueError, KeyError):
                records_skipped += 1

        _, graph_summary = ingest_event_records(events, graph)
        evidence_records = build_real_data_evidence(events, graph, persist=False)
        evidence_gaps = [
            record
            for record in evidence_records
            if not record.related_entities.mitre_techniques
        ]
        summary = {
            "records_received": len(alerts),
            "records_parsed": len(events),
            "records_skipped": records_skipped,
            "events_added": int(graph_summary.get("events_added", 0)),
            "techniques_added": int(graph_summary.get("techniques_added", 0)),
            "relationships_added": int(graph_summary.get("relationships_added", 0)),
            "duplicates_skipped": int(graph_summary.get("duplicates_skipped", 0)),
            "evidence_records_created": len(evidence_records),
            "evidence_gaps_created": len(evidence_gaps),
        }
        self._write_pipeline_report(alerts, summary, evidence_records)
        return {
            **summary,
            "status": "accepted",
            "message": "Ingestion complete. Dashboard will refresh within 30 seconds.",
        }

    @staticmethod
    def _alerts_from_payload(payload: dict[str, Any] | list[Any]) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
        msg = "Wazuh ingestion payload must be a JSON object or list of objects."
        raise ValueError(msg)

    @staticmethod
    def _has_required_fields(alert: dict[str, Any]) -> bool:
        rule = alert.get("rule") if isinstance(alert.get("rule"), dict) else {}
        agent = alert.get("agent") if isinstance(alert.get("agent"), dict) else {}
        return bool(alert.get("timestamp") and rule.get("id") and agent.get("name"))

    def _write_pipeline_report(
        self,
        alerts: list[Any],
        summary: dict[str, int],
        evidence_records: list[Any],
    ) -> None:
        output = {
            "schema_version": "1.0",
            "source_path": "POST /ingest/wazuh",
            "summary": {
                "records_read": summary["records_received"],
                "records_parsed": summary["records_parsed"],
                "records_skipped": summary["records_skipped"],
                "events_added": summary["events_added"],
                "techniques_added": summary["techniques_added"],
                "relationships_added": summary["relationships_added"],
                "duplicates_skipped": summary["duplicates_skipped"],
                "evidence_records_created": summary["evidence_records_created"],
                "evidence_gaps_created": summary["evidence_gaps_created"],
            },
            "evidence_records": [record.to_dict() for record in evidence_records],
            "raw_records_received": len(alerts),
            "explanation": (
                "Wazuh alerts were received through the runtime API, normalized, "
                "added to a Knowledge Graph, and converted into Evidence Layer records."
            ),
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(output, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _repository_modules(self) -> dict[str, Any]:
        if self._parser and self._graph_ingestor and self._evidence_builder and self._graph_factory:
            return {}

        root_core = self.repository_root / "core"
        preserved_modules = {
            name: sys.modules.get(name)
            for name in (
                "core",
                "core.ingest",
                "core.ingest.wazuh_parser",
                "core.ingest.graph_ingest",
                "core.ingest.real_data_evidence",
                "core.knowledge_graph",
                "core.evidence_schema",
            )
        }
        try:
            core_package = types.ModuleType("core")
            core_package.__path__ = [str(root_core)]
            sys.modules["core"] = core_package

            ingest_package = types.ModuleType("core.ingest")
            ingest_package.__path__ = [str(root_core / "ingest")]
            sys.modules["core.ingest"] = ingest_package

            wazuh_parser = self._load_module(
                "core.ingest.wazuh_parser",
                root_core / "ingest" / "wazuh_parser.py",
            )
            knowledge_graph = self._load_module(
                "core.knowledge_graph",
                root_core / "knowledge_graph.py",
            )
            graph_ingest = self._load_module(
                "core.ingest.graph_ingest",
                root_core / "ingest" / "graph_ingest.py",
            )
            real_data_evidence = self._load_module(
                "core.ingest.real_data_evidence",
                root_core / "ingest" / "real_data_evidence.py",
            )
            return {
                "parse_wazuh_alert": wazuh_parser.parse_wazuh_alert,
                "KnowledgeGraph": knowledge_graph.KnowledgeGraph,
                "ingest_event_records": graph_ingest.ingest_event_records,
                "build_real_data_evidence": real_data_evidence.build_real_data_evidence,
            }
        finally:
            for name, module in preserved_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    @staticmethod
    def _load_module(name: str, path: Path) -> Any:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            msg = f"Unable to load module {name} from {path}"
            raise ImportError(msg)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
