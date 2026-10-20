"""Runtime API adapter for AWS GuardDuty finding ingestion."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

from huginn_muninn_api.core.repository_module_lock import repository_module_transaction


class GuardDutyIngestApi:
    """Parse GuardDuty findings and publish the live telemetry report format."""

    def __init__(self, repository_root: str | Path) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.output_path = self.repository_root / "reports" / "real-data-pipeline-output.json"

    def ingest(self, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        """Ingest one GuardDuty finding or a list of findings."""

        findings = self._findings_from_payload(payload)
        modules = self._repository_modules()
        parser = modules["AwsGuardDutyParser"]()
        ingest_event_records = modules["ingest_event_records"]
        build_real_data_evidence = modules["build_real_data_evidence"]

        valid_findings = []
        records_skipped = 0
        for finding in findings:
            if not isinstance(finding, dict):
                records_skipped += 1
                continue
            if not self._has_required_fields(finding):
                records_skipped += 1
                continue
            valid_findings.append(finding)

        events = parser.parse_findings(valid_findings)
        records_skipped += len(valid_findings) - len(events)

        graph_summary, evidence_records = self._persist_events(
            events,
            modules,
            ingest_event_records,
            build_real_data_evidence,
        )
        evidence_gaps = [
            record
            for record in evidence_records
            if not record.related_entities.mitre_techniques
        ]
        response_summary = self._build_summary(
            records_received=len(findings),
            records_parsed=len(events),
            records_skipped=records_skipped,
            graph_summary=graph_summary,
            evidence_records_created=len(evidence_records),
            evidence_gaps_created=len(evidence_gaps),
        )
        self._write_pipeline_report(
            records_received=len(findings),
            response_summary=response_summary,
            graph_summary=graph_summary,
            evidence_records=evidence_records,
        )
        return response_summary

    @staticmethod
    def _findings_from_payload(payload: dict[str, Any] | list[Any]) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
        msg = "GuardDuty ingestion payload must be a JSON object or list of objects."
        raise ValueError(msg)

    @staticmethod
    def _has_required_fields(finding: dict[str, Any]) -> bool:
        finding_id = finding.get("id") or finding.get("Id")
        finding_type = finding.get("type") or finding.get("Type")
        return bool(finding_id and finding_type)

    @staticmethod
    def _build_summary(
        *,
        records_received: int,
        records_parsed: int,
        records_skipped: int,
        graph_summary: dict[str, int],
        evidence_records_created: int,
        evidence_gaps_created: int,
    ) -> dict[str, Any]:
        return {
            "status": "accepted",
            "source": "aws_guardduty",
            "records_received": records_received,
            "records_parsed": records_parsed,
            "records_skipped": records_skipped,
            "events_added": int(graph_summary.get("events_added", 0)),
            "techniques_added": int(graph_summary.get("techniques_added", 0)),
            "evidence_records_created": evidence_records_created,
            "evidence_gaps_created": evidence_gaps_created,
            "message": "Ingestion complete. Dashboard will refresh within 30 seconds.",
        }

    def _write_pipeline_report(
        self,
        *,
        records_received: int,
        response_summary: dict[str, Any],
        graph_summary: dict[str, int],
        evidence_records: list[Any],
    ) -> None:
        output = {
            "schema_version": "1.0",
            "source_path": "POST /ingest/guardduty",
            "summary": {
                "records_read": records_received,
                "records_parsed": response_summary["records_parsed"],
                "records_skipped": response_summary["records_skipped"],
                "events_added": response_summary["events_added"],
                "techniques_added": response_summary["techniques_added"],
                "relationships_added": int(graph_summary.get("relationships_added", 0)),
                "duplicates_skipped": int(graph_summary.get("duplicates_skipped", 0)),
                "evidence_records_created": response_summary["evidence_records_created"],
                "evidence_gaps_created": response_summary["evidence_gaps_created"],
            },
            "evidence_records": [record.to_dict() for record in evidence_records],
            "raw_records_received": records_received,
            "explanation": (
                "GuardDuty findings were received through the runtime API, normalized, "
                "added to a Knowledge Graph, and converted into Evidence Layer records."
            ),
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(
            json.dumps(output, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _persist_events(
        self,
        events: list[Any],
        modules: dict[str, Any],
        ingest_event_records: Any,
        build_real_data_evidence: Any,
    ) -> tuple[dict[str, int], list[Any]]:
        if "FileLock" not in modules:
            graph = self._load_persistent_graph(modules)
            _, graph_summary = ingest_event_records(events, graph)
            evidence_records = build_real_data_evidence(events, graph, persist=False)
            return graph_summary, evidence_records

        lock_path = self.repository_root / "reports" / ".ingestion-artifacts.lock"
        with modules["FileLock"](lock_path):
            graph = self._load_persistent_graph(modules)
            _, graph_summary = ingest_event_records(events, graph)
            evidence_records = build_real_data_evidence(events, graph, persist=False)
            self._persist_graph(graph, modules)
            self._merge_evidence_index(evidence_records, modules)
        return graph_summary, evidence_records

    def _load_persistent_graph(self, modules: dict[str, Any]) -> Any:
        graph_path = self.repository_root / "reports" / "knowledge-graph.json"
        if "load_graph" in modules and graph_path.exists():
            return modules["load_graph"](graph_path)
        return modules["KnowledgeGraph"]()

    def _persist_graph(self, graph: Any, modules: dict[str, Any]) -> None:
        if "load_graph" not in modules:
            return

        graph_path = self.repository_root / "reports" / "knowledge-graph.json"
        summary_path = (
            self.repository_root / "core" / "patterns" / "knowledge-graph-summary.json"
        )
        graph.save(graph_path)
        modules["atomic_write_json"](summary_path, graph.summary())

    def _merge_evidence_index(
        self,
        evidence_records: list[Any],
        modules: dict[str, Any],
    ) -> None:
        if "merge_evidence_records" not in modules:
            return

        evidence_path = self.repository_root / "reports" / "evidence-index.json"
        existing_records = (
            modules["load_evidence_index"](evidence_path)
            if evidence_path.exists()
            else []
        )
        merged_records = modules["merge_evidence_records"](
            existing_records,
            evidence_records,
        )
        modules["save_evidence_index"](evidence_path, merged_records)

    def _repository_modules(self) -> dict[str, Any]:
        root_core = self.repository_root / "core"
        with repository_module_transaction():
            core_package = types.ModuleType("core")
            core_package.__path__ = [str(root_core)]
            sys.modules["core"] = core_package

            ingest_package = types.ModuleType("core.ingest")
            ingest_package.__path__ = [str(root_core / "ingest")]
            sys.modules["core.ingest"] = ingest_package

            guardduty_parser = self._load_module(
                "core.ingest.aws_guardduty_parser",
                root_core / "ingest" / "aws_guardduty_parser.py",
            )
            json_persistence = self._load_module(
                "core.json_persistence",
                root_core / "json_persistence.py",
            )
            knowledge_graph = self._load_module(
                "core.knowledge_graph",
                root_core / "knowledge_graph.py",
            )
            evidence_schema = self._load_module(
                "core.evidence_schema",
                root_core / "evidence_schema.py",
            )
            graph_ingest = self._load_module(
                "core.ingest.graph_ingest",
                root_core / "ingest" / "graph_ingest.py",
            )
            real_data_evidence = self._load_module(
                "core.ingest.real_data_evidence",
                root_core / "ingest" / "real_data_evidence.py",
            )
            graph_intelligence = self._load_module(
                "core.graph_intelligence",
                root_core / "graph_intelligence.py",
            )
            return {
                "AwsGuardDutyParser": guardduty_parser.AwsGuardDutyParser,
                "KnowledgeGraph": knowledge_graph.KnowledgeGraph,
                "FileLock": json_persistence.FileLock,
                "atomic_write_json": json_persistence.atomic_write_json,
                "load_graph": graph_intelligence.load_graph,
                "ingest_event_records": graph_ingest.ingest_event_records,
                "build_real_data_evidence": real_data_evidence.build_real_data_evidence,
                "load_evidence_index": evidence_schema.load_evidence_index,
                "merge_evidence_records": evidence_schema.merge_evidence_records,
                "save_evidence_index": evidence_schema.save_evidence_index,
            }

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
