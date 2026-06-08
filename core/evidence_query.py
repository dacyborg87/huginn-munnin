"""Read-only queries over existing evidence records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.evidence_schema import (
    ConfidenceLevel,
    EvidenceRecord,
    load_evidence_index,
)


DEFAULT_EVIDENCE_PATHS = (
    Path("reports/evidence-builder-output.json"),
    Path("reports/evidence-index.json"),
)
DEFAULT_QUERY_OUTPUT_PATH = Path("reports/evidence-query-output.json")


@dataclass(frozen=True)
class EvidenceQueryResult:
    """A query response with matching evidence and a simple explanation."""

    query_type: str
    query_value: str
    matches: list[EvidenceRecord]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_type": self.query_type,
            "query_value": self.query_value,
            "match_count": len(self.matches),
            "matches": [record.to_dict() for record in self.matches],
            "explanation": self.explanation,
        }


class EvidenceQuery:
    """Small MVP query layer for JSON-backed evidence records."""

    def __init__(
        self,
        repository_root: Path | str = ".",
        evidence_paths: tuple[Path, ...] = DEFAULT_EVIDENCE_PATHS,
    ) -> None:
        self.repository_root = Path(repository_root)
        self.evidence_paths = evidence_paths
        self.records = self._load_records()

    def find_by_finding_id(self, finding_id: str) -> EvidenceQueryResult:
        """Find evidence tied to a finding, source reference, or evidence ID."""

        normalized = _normalize_entity_id(finding_id)
        matches = [
            record
            for record in self.records
            if normalized
            in {
                record.evidence_id,
                record.source_reference,
                *record.related_entities.all_entity_ids(),
            }
        ]
        return self._result(
            "finding_id",
            finding_id,
            matches,
            f"This found evidence records connected to finding {finding_id!r}.",
        )

    def find_by_mitre_technique(self, technique_id: str) -> EvidenceQueryResult:
        normalized = _normalize_mitre_id(technique_id)
        matches = [
            record
            for record in self.records
            if normalized in record.related_entities.mitre_techniques
        ]
        return self._result(
            "mitre_technique",
            technique_id,
            matches,
            f"This found evidence records connected to MITRE technique {normalized!r}.",
        )

    def find_by_related_weakness(self, weakness_id: str) -> EvidenceQueryResult:
        normalized = _normalize_weakness_id(weakness_id)
        matches = [
            record
            for record in self.records
            if normalized in record.related_entities.architecture_weaknesses
            or normalized == record.source_reference
        ]
        return self._result(
            "related_weakness",
            weakness_id,
            matches,
            f"This found evidence records connected to weakness {normalized!r}.",
        )

    def find_by_recommendation(self, recommendation_id: str) -> EvidenceQueryResult:
        normalized = _normalize_recommendation_id(recommendation_id)
        matches = [
            record
            for record in self.records
            if normalized in record.related_entities.defense_recommendations
            or normalized == record.source_reference
        ]
        return self._result(
            "recommendation",
            recommendation_id,
            matches,
            f"This found evidence records connected to recommendation {normalized!r}.",
        )

    def find_by_confidence_level(
        self,
        confidence_level: ConfidenceLevel | str,
    ) -> EvidenceQueryResult:
        level = (
            confidence_level
            if isinstance(confidence_level, ConfidenceLevel)
            else ConfidenceLevel(str(confidence_level).lower())
        )
        matches = [
            record
            for record in self.records
            if record.confidence.level == level
        ]
        return self._result(
            "confidence_level",
            level.value,
            matches,
            f"This found evidence records with {level.value!r} confidence.",
        )

    def save_sample_query_output(
        self,
        path: Path | str | None = None,
    ) -> dict[str, Any]:
        output = {
            "evidence_record_count": len(self.records),
            "queries": [
                self.find_by_mitre_technique("T1078").to_dict(),
                self.find_by_related_weakness(
                    "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
                ).to_dict(),
                self.find_by_recommendation(
                    "recommendation:design.post_auth_telemetry_layer"
                ).to_dict(),
                self.find_by_confidence_level("high").to_dict(),
                self.find_by_finding_id("finding:does-not-exist").to_dict(),
            ],
        }
        output_path = self.repository_root / (path or DEFAULT_QUERY_OUTPUT_PATH)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return output

    def _load_records(self) -> list[EvidenceRecord]:
        records_by_id: dict[str, EvidenceRecord] = {}
        for path in self.evidence_paths:
            full_path = self.repository_root / path
            if not full_path.exists():
                continue
            for record in load_evidence_index(full_path):
                records_by_id.setdefault(record.evidence_id, record)
        return [
            records_by_id[evidence_id]
            for evidence_id in sorted(records_by_id)
        ]

    def _result(
        self,
        query_type: str,
        query_value: str,
        matches: list[EvidenceRecord],
        success_explanation: str,
    ) -> EvidenceQueryResult:
        if matches:
            explanation = (
                f"{success_explanation} Huginn can use these records as proof "
                "for analysis, recommendations, or future investigation steps."
            )
        else:
            explanation = (
                f"No evidence records matched {query_value!r}. Huginn should treat "
                "this as an evidence gap, not as proof that the activity is safe."
            )
        return EvidenceQueryResult(
            query_type=query_type,
            query_value=query_value,
            matches=matches,
            explanation=explanation,
        )


def load_evidence_query(repository_root: Path | str = ".") -> EvidenceQuery:
    return EvidenceQuery(repository_root)


def generate_sample_evidence_query_output(
    repository_root: Path | str = ".",
) -> dict[str, Any]:
    return EvidenceQuery(repository_root).save_sample_query_output()


def _normalize_mitre_id(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("mitre:"):
        return stripped
    return f"mitre:{stripped}"


def _normalize_weakness_id(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("weakness:"):
        return stripped
    return f"weakness:{stripped}"


def _normalize_recommendation_id(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("recommendation:"):
        return stripped
    return f"recommendation:{stripped}"


def _normalize_entity_id(value: str) -> str:
    stripped = value.strip()
    if ":" in stripped:
        return stripped
    if stripped.startswith("T") and stripped[1:].isdigit():
        return _normalize_mitre_id(stripped)
    return stripped
