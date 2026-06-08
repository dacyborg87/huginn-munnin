"""Build evidence records from existing graph intelligence artifacts."""

from __future__ import annotations

from pathlib import Path

from core.evidence_schema import (
    ConfidenceBreakdown,
    ConfidenceFactor,
    EvidenceRecord,
    EvidenceSourceType,
    RelatedEvidenceEntities,
    confidence_level_for_score,
    save_evidence_index,
)
from core.graph_intelligence import GraphIntelligence
from core.knowledge_graph import KnowledgeNode


DEFAULT_OUTPUT_PATH = Path("reports/evidence-builder-output.json")


class EvidenceBuilder:
    """Small MVP builder that turns graph relationships into evidence records."""

    def __init__(self, repository_root: Path | str = ".") -> None:
        self.repository_root = Path(repository_root)
        self.intelligence = GraphIntelligence.from_repository(self.repository_root)
        self.graph = self.intelligence.graph

    def build(self, persist: bool = True) -> list[EvidenceRecord]:
        records = [
            self._record_for_weakness(node)
            for node in sorted(self.graph.nodes.values(), key=lambda item: item.node_id)
            if node.node_type == "Architecture Weakness"
        ]
        if persist:
            save_evidence_index(self.repository_root / DEFAULT_OUTPUT_PATH, records)
        return records

    def _record_for_weakness(self, weakness: KnowledgeNode) -> EvidenceRecord:
        related = self._related_entities_for_weakness(weakness.node_id)
        confidence = self._confidence_for_weakness(weakness, related)
        technique_labels = self._labels_for(related.mitre_techniques)
        recommendation_labels = self._labels_for(related.defense_recommendations)
        title = f"Evidence for architecture weakness: {weakness.label}"
        summary = (
            f"{weakness.label} is supported by graph relationships involving "
            f"{_join_or_fallback(technique_labels, 'no MITRE techniques')}, "
            f"{len(related.events)} event(s), {len(related.memory_entries)} memory entry "
            f"or entries, and recommendations including "
            f"{_join_or_fallback(recommendation_labels, 'no recommendations')}."
        )
        return EvidenceRecord(
            evidence_id=f"evidence:{_slug(weakness.node_id)}",
            title=title,
            summary=summary,
            source_type=EvidenceSourceType.ARCHITECTURE_REPORT,
            source_path="reports/graph-intelligence-report.json",
            source_reference=weakness.node_id,
            timestamp=self._timestamp_for(related),
            related_entities=related,
            confidence=confidence,
        )

    def _related_entities_for_weakness(self, weakness_id: str) -> RelatedEvidenceEntities:
        techniques: set[str] = set()
        attack_chains: set[str] = set()
        recommendations: set[str] = set()
        memory_entries: set[str] = set()

        for relationship in self.graph.relationships.values():
            if relationship.relationship_type == "weakens" and relationship.source_id == weakness_id:
                target = self.graph.nodes.get(relationship.target_id)
                if target and target.node_type == "MITRE Technique":
                    techniques.add(target.node_id)
                elif target and target.node_type == "Attack Chain":
                    attack_chains.add(target.node_id)
            elif (
                relationship.relationship_type == "recommends"
                and relationship.target_id == weakness_id
            ):
                recommendations.add(relationship.source_id)
            elif (
                relationship.relationship_type == "caused_by"
                and relationship.source_id == weakness_id
            ):
                target = self.graph.nodes.get(relationship.target_id)
                if target and target.node_type == "Memory Entry":
                    memory_entries.add(target.node_id)

        attack_chains.update(self._attack_chains_for_techniques(techniques))
        events = self._events_for_techniques(techniques)
        memory_entries.update(self._memory_entries_for_targets({*techniques, *attack_chains}))

        return RelatedEvidenceEntities(
            events=sorted(events),
            mitre_techniques=sorted(techniques),
            attack_chains=sorted(attack_chains),
            memory_entries=sorted(memory_entries),
            architecture_weaknesses=[weakness_id],
            defense_recommendations=sorted(recommendations),
        )

    def _events_for_techniques(self, technique_ids: set[str]) -> set[str]:
        events: set[str] = set()
        for relationship in self.graph.relationships.values():
            if relationship.relationship_type != "relates_to":
                continue
            if relationship.target_id not in technique_ids:
                continue
            source = self.graph.nodes.get(relationship.source_id)
            if source and source.node_type == "Event":
                events.add(source.node_id)
        return events

    def _attack_chains_for_techniques(self, technique_ids: set[str]) -> set[str]:
        attack_chains: set[str] = set()
        for relationship in self.graph.relationships.values():
            if relationship.relationship_type != "relates_to":
                continue
            if relationship.target_id not in technique_ids:
                continue
            source = self.graph.nodes.get(relationship.source_id)
            if source and source.node_type == "Attack Chain":
                attack_chains.add(source.node_id)
        return attack_chains

    def _memory_entries_for_targets(self, target_ids: set[str]) -> set[str]:
        memory_entries: set[str] = set()
        for relationship in self.graph.relationships.values():
            if relationship.relationship_type != "previously_seen_as":
                continue
            if relationship.target_id not in target_ids:
                continue
            source = self.graph.nodes.get(relationship.source_id)
            if source and source.node_type == "Memory Entry":
                memory_entries.add(source.node_id)
        return memory_entries

    def _confidence_for_weakness(
        self,
        weakness: KnowledgeNode,
        related: RelatedEvidenceEntities,
    ) -> ConfidenceBreakdown:
        severity = str(weakness.properties.get("severity", "")).lower()
        severity_value = {"critical": 1.0, "high": 0.85, "medium": 0.65}.get(severity, 0.4)
        correlation_value = min(1.0, len(related.all_entity_ids()) / 8)
        repeat_value = 1.0 if related.memory_entries else 0.35
        calculation = {
            "source_reliability": _factor(0.30, 1.0),
            "entity_correlation": _factor(0.25, correlation_value),
            "repeat_observation": _factor(0.20, repeat_value),
            "recency": _factor(0.10, 0.8),
            "severity_alignment": _factor(0.15, severity_value),
        }
        score = round(sum(factor.weighted_score for factor in calculation.values()), 3)
        return ConfidenceBreakdown(
            score=score,
            level=confidence_level_for_score(score),
            calculation=calculation,
            explanation=(
                f"Confidence is {confidence_level_for_score(score).value} because "
                f"{weakness.label!r} is connected to {len(related.mitre_techniques)} "
                f"MITRE technique(s), {len(related.events)} event(s), "
                f"{len(related.defense_recommendations)} recommendation(s), and "
                f"{len(related.memory_entries)} memory entry or entries."
            ),
        )

    def _timestamp_for(self, related: RelatedEvidenceEntities) -> str:
        for event_id in related.events:
            event = self.graph.nodes.get(event_id)
            timestamp = event.properties.get("timestamp") if event else None
            if timestamp:
                return str(timestamp)
        return "2026-06-01T00:00:00Z"

    def _labels_for(self, node_ids: list[str]) -> list[str]:
        return [
            self.graph.nodes[node_id].label
            for node_id in node_ids
            if node_id in self.graph.nodes
        ]


def build_evidence_from_graph(
    repository_root: Path | str = ".",
    *,
    persist: bool = True,
) -> list[EvidenceRecord]:
    return EvidenceBuilder(repository_root).build(persist=persist)


def _factor(weight: float, value: float) -> ConfidenceFactor:
    return ConfidenceFactor(
        weight=weight,
        value=value,
        weighted_score=round(weight * value, 3),
    )


def _slug(value: str) -> str:
    return (
        value.replace(":", "-")
        .replace("/", "-")
        .replace("_", "-")
        .replace(".", "-")
    )


def _join_or_fallback(values: list[str], fallback: str) -> str:
    if not values:
        return fallback
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f", and {values[-1]}"
