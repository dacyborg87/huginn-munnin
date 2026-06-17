"""Runtime API adapter for AWS GuardDuty finding ingestion."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any
import types


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
        graph = modules["KnowledgeGraph"]()

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

        _, graph_summary = ingest_event_records(events, graph)
        evidence_records = build_real_data_evidence(events, graph, persist=False)
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

    def _repository_modules(self) -> dict[str, Any]:
        root_core = self.repository_root / "core"
        preserved_modules = {
            name: sys.modules.get(name)
            for name in (
                "core",
                "core.ingest",
                "core.ingest.aws_guardduty_parser",
                "core.ingest.graph_ingest",
                "core.ingest.real_data_evidence",
                "core.ingest.wazuh_parser",
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

            guardduty_parser = self._load_module(
                "core.ingest.aws_guardduty_parser",
                root_core / "ingest" / "aws_guardduty_parser.py",
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
                "AwsGuardDutyParser": guardduty_parser.AwsGuardDutyParser,
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
