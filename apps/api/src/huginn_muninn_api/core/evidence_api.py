"""Read-only API helpers for existing evidence query artifacts."""

from __future__ import annotations

from collections import Counter
import importlib.util
from pathlib import Path
import sys
from typing import Any
import types


class EvidenceApi:
    """Expose evidence query results as simple JSON-ready dictionaries."""

    def __init__(self, repository_root: Path | str) -> None:
        self.repository_root = Path(repository_root)

    def summary(self) -> dict[str, Any]:
        query = self._query()
        confidence_counts = Counter(
            record.confidence.level.value for record in query.records
        )
        source_type_counts = Counter(record.source_type.value for record in query.records)
        return {
            "entity_searched": "evidence",
            "summary": {
                "total_records": len(query.records),
                "confidence_counts": dict(sorted(confidence_counts.items())),
                "source_type_counts": dict(sorted(source_type_counts.items())),
            },
            "evidence_records": [record.to_dict() for record in query.records],
            "match_count": len(query.records),
            "explanation": (
                "This shows how many evidence records Huginn can search and "
                "how those records are grouped by confidence and source type."
            ),
        }

    def finding(self, finding_id: str) -> dict[str, Any]:
        return self._result_to_response(self._query().find_by_finding_id(finding_id))

    def mitre(self, technique_id: str) -> dict[str, Any]:
        return self._result_to_response(
            self._query().find_by_mitre_technique(technique_id)
        )

    def weakness(self, weakness_id: str) -> dict[str, Any]:
        return self._result_to_response(
            self._query().find_by_related_weakness(weakness_id)
        )

    def recommendation(self, recommendation_id: str) -> dict[str, Any]:
        return self._result_to_response(
            self._query().find_by_recommendation(recommendation_id)
        )

    def confidence(self, level: str) -> dict[str, Any]:
        return self._result_to_response(self._query().find_by_confidence_level(level))

    def _query(self) -> Any:
        evidence_query = self._load_repository_evidence_query()
        return evidence_query(self.repository_root)

    @staticmethod
    def _result_to_response(result: Any) -> dict[str, Any]:
        payload = result.to_dict()
        return {
            "entity_searched": payload["query_value"],
            "query_type": payload["query_type"],
            "evidence_records": payload["matches"],
            "match_count": payload["match_count"],
            "explanation": payload["explanation"],
        }

    def _load_repository_evidence_query(self) -> Any:
        root_core = self.repository_root / "core"
        preserved_modules = {
            name: sys.modules.get(name)
            for name in ("core", "core.evidence_schema", "core.evidence_query")
        }
        try:
            core_package = types.ModuleType("core")
            core_package.__path__ = [str(root_core)]
            sys.modules["core"] = core_package
            self._load_module("core.evidence_schema", root_core / "evidence_schema.py")
            query_module = self._load_module(
                "core.evidence_query",
                root_core / "evidence_query.py",
            )
            return query_module.EvidenceQuery
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
