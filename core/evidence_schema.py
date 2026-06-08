"""Schema objects for traceable evidence records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


class EvidenceSourceType(StrEnum):
    SOC_EVENT = "soc_event"
    LAB_EVENT = "lab_event"
    DETECTION_ALERT = "detection_alert"
    ATTACK_CHAIN_REPORT = "attack_chain_report"
    COVERAGE_REPORT = "coverage_report"
    GAP_REPORT = "gap_report"
    ARCHITECTURE_REPORT = "architecture_report"
    DEFENSE_RECOMMENDATION = "defense_recommendation"
    MEMORY_PATTERN = "memory_pattern"
    ANALYST_NOTE = "analyst_note"
    SCREENSHOT_REFERENCE = "screenshot_reference"
    COMMAND_OUTPUT = "command_output"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ConfidenceFactor:
    """One weighted input used to explain a confidence score."""

    weight: float
    value: float
    weighted_score: float

    def __post_init__(self) -> None:
        _validate_range("weight", self.weight)
        _validate_range("value", self.value)
        _validate_range("weighted_score", self.weighted_score)

    def to_dict(self) -> dict[str, float]:
        return {
            "weight": self.weight,
            "value": self.value,
            "weighted_score": self.weighted_score,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ConfidenceFactor:
        return cls(
            weight=float(payload["weight"]),
            value=float(payload["value"]),
            weighted_score=float(payload["weighted_score"]),
        )


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """Explainable confidence score and supporting calculation."""

    score: float
    level: ConfidenceLevel
    calculation: dict[str, ConfidenceFactor]
    explanation: str

    def __post_init__(self) -> None:
        _validate_range("score", self.score)
        if self.level != confidence_level_for_score(self.score):
            msg = (
                f"Confidence level {self.level.value!r} does not match "
                f"score {self.score:.2f}"
            )
            raise ValueError(msg)
        if not self.explanation.strip():
            msg = "Confidence explanation is required."
            raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "level": self.level.value,
            "calculation": {
                name: factor.to_dict()
                for name, factor in sorted(self.calculation.items())
            },
            "explanation": self.explanation,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ConfidenceBreakdown:
        return cls(
            score=float(payload["score"]),
            level=ConfidenceLevel(payload["level"]),
            calculation={
                str(name): ConfidenceFactor.from_dict(dict(factor))
                for name, factor in payload.get("calculation", {}).items()
            },
            explanation=str(payload["explanation"]),
        )


@dataclass(frozen=True)
class RelatedEvidenceEntities:
    """Graph entity IDs connected to one evidence record."""

    events: list[str] = field(default_factory=list)
    mitre_techniques: list[str] = field(default_factory=list)
    attack_chains: list[str] = field(default_factory=list)
    memory_entries: list[str] = field(default_factory=list)
    architecture_weaknesses: list[str] = field(default_factory=list)
    defense_recommendations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.all_entity_ids():
            msg = "Evidence must link to at least one graph entity."
            raise ValueError(msg)

    def all_entity_ids(self) -> list[str]:
        return [
            *self.events,
            *self.mitre_techniques,
            *self.attack_chains,
            *self.memory_entries,
            *self.architecture_weaknesses,
            *self.defense_recommendations,
        ]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "events": sorted(self.events),
            "mitre_techniques": sorted(self.mitre_techniques),
            "attack_chains": sorted(self.attack_chains),
            "memory_entries": sorted(self.memory_entries),
            "architecture_weaknesses": sorted(self.architecture_weaknesses),
            "defense_recommendations": sorted(self.defense_recommendations),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RelatedEvidenceEntities:
        return cls(
            events=list(payload.get("events", [])),
            mitre_techniques=list(payload.get("mitre_techniques", [])),
            attack_chains=list(payload.get("attack_chains", [])),
            memory_entries=list(payload.get("memory_entries", [])),
            architecture_weaknesses=list(payload.get("architecture_weaknesses", [])),
            defense_recommendations=list(payload.get("defense_recommendations", [])),
        )


@dataclass(frozen=True)
class EvidenceRecord:
    """One traceable proof item supporting a finding or recommendation."""

    evidence_id: str
    title: str
    summary: str
    source_type: EvidenceSourceType
    source_path: str
    source_reference: str
    timestamp: str
    related_entities: RelatedEvidenceEntities
    confidence: ConfidenceBreakdown

    def __post_init__(self) -> None:
        if not self.evidence_id.startswith("evidence:"):
            msg = "Evidence IDs must start with 'evidence:'."
            raise ValueError(msg)
        for field_name in ("title", "summary", "source_path", "source_reference", "timestamp"):
            if not str(getattr(self, field_name)).strip():
                msg = f"{field_name} is required."
                raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "summary": self.summary,
            "source_type": self.source_type.value,
            "source_path": self.source_path,
            "source_reference": self.source_reference,
            "timestamp": self.timestamp,
            "related_entities": self.related_entities.to_dict(),
            "confidence": self.confidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidenceRecord:
        return cls(
            evidence_id=str(payload["evidence_id"]),
            title=str(payload["title"]),
            summary=str(payload["summary"]),
            source_type=EvidenceSourceType(payload["source_type"]),
            source_path=str(payload["source_path"]),
            source_reference=str(payload["source_reference"]),
            timestamp=str(payload["timestamp"]),
            related_entities=RelatedEvidenceEntities.from_dict(
                dict(payload["related_entities"])
            ),
            confidence=ConfidenceBreakdown.from_dict(dict(payload["confidence"])),
        )


def confidence_level_for_score(score: float) -> ConfidenceLevel:
    _validate_range("score", score)
    if score < 0.4:
        return ConfidenceLevel.LOW
    if score < 0.7:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.HIGH


def evidence_index_to_dict(records: list[EvidenceRecord]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence": [
            record.to_dict()
            for record in sorted(records, key=lambda item: item.evidence_id)
        ],
    }


def load_evidence_index(path: Path | str) -> list[EvidenceRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        EvidenceRecord.from_dict(dict(record))
        for record in payload.get("evidence", [])
    ]


def save_evidence_index(path: Path | str, records: list[EvidenceRecord]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(evidence_index_to_dict(records), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _validate_range(name: str, value: float) -> None:
    if not 0 <= value <= 1:
        msg = f"{name} must be between 0 and 1."
        raise ValueError(msg)
