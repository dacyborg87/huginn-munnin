"""Read-only query helpers for the Munnin knowledge graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.graph_context_builder import GraphContextBuilder
from core.knowledge_graph import KnowledgeGraph


class GraphIntelligence:
    """Answer simple questions using the existing in-memory knowledge graph."""

    def __init__(self, graph: KnowledgeGraph) -> None:
        self.graph = graph

    @classmethod
    def from_repository(cls, repository_root: Path | str = ".") -> GraphIntelligence:
        graph_path = Path(repository_root) / "reports" / "knowledge-graph.json"
        if graph_path.exists():
            return cls(load_graph(graph_path))
        return cls(GraphContextBuilder(repository_root).build(persist=False))

    def find_related_entities(self, entity_id: str) -> list[dict[str, Any]]:
        """Return directly connected nodes for an entity."""

        node_id = self._normalize_entity_id(entity_id)
        related: list[dict[str, Any]] = []
        for relationship in self.graph.relationships.values():
            if relationship.source_id == node_id:
                related.append(
                    self._related_entity(
                        relationship.target_id,
                        relationship.relationship_type,
                        direction="outgoing",
                    )
                )
            elif relationship.target_id == node_id:
                related.append(
                    self._related_entity(
                        relationship.source_id,
                        relationship.relationship_type,
                        direction="incoming",
                    )
                )
        return self._deduplicate_entities(related)

    def find_connected_weaknesses(self, event_or_technique: str) -> list[dict[str, Any]]:
        """Find architecture weaknesses connected to an event or MITRE technique."""

        node_id = self._normalize_entity_id(event_or_technique)
        technique_ids = {node_id} if node_id.startswith("mitre:") else set()
        technique_ids.update(
            item["id"]
            for item in self.find_related_entities(node_id)
            if item["type"] == "MITRE Technique"
        )

        weakness_ids = set()
        for relationship in self.graph.relationships.values():
            if relationship.relationship_type != "weakens":
                continue
            if relationship.target_id == node_id or relationship.target_id in technique_ids:
                weakness_ids.add(relationship.source_id)

        return [
            self._node_result(weakness_id)
            for weakness_id in sorted(weakness_ids)
            if self.graph.nodes[weakness_id].node_type == "Architecture Weakness"
        ]

    def find_recommendations_for_technique(self, technique_id: str) -> list[dict[str, Any]]:
        """Find defense recommendations that address weaknesses tied to a technique."""

        weakness_ids = {
            weakness["id"]
            for weakness in self.find_connected_weaknesses(self._normalize_entity_id(technique_id))
        }
        recommendation_ids = set()
        for relationship in self.graph.relationships.values():
            if (
                relationship.relationship_type == "recommends"
                and relationship.target_id in weakness_ids
            ):
                recommendation_ids.add(relationship.source_id)

        return [
            self._node_result(recommendation_id)
            for recommendation_id in sorted(recommendation_ids)
            if self.graph.nodes[recommendation_id].node_type == "Defense Recommendation"
        ]

    def find_similar_incidents(self, event_id: str) -> list[dict[str, Any]]:
        """Find other event nodes that share MITRE technique context with an event."""

        node_id = self._normalize_entity_id(event_id)
        technique_ids = {
            item["id"]
            for item in self.find_related_entities(node_id)
            if item["type"] == "MITRE Technique"
        }
        if not technique_ids:
            return []

        similar: dict[str, dict[str, Any]] = {}
        for relationship in self.graph.relationships.values():
            if relationship.relationship_type != "relates_to":
                continue
            if relationship.target_id not in technique_ids:
                continue
            candidate = self.graph.nodes.get(relationship.source_id)
            if candidate is None or candidate.node_type != "Event" or candidate.node_id == node_id:
                continue
            result = similar.setdefault(
                candidate.node_id,
                {
                    **self._node_result(candidate.node_id),
                    "shared_techniques": [],
                    "similarity_reason": "Shares MITRE technique context with the source event.",
                },
            )
            result["shared_techniques"].append(self._node_result(relationship.target_id))

        return sorted(
            similar.values(),
            key=lambda item: (-len(item["shared_techniques"]), item["id"]),
        )

    def sample_report(self) -> dict[str, Any]:
        """Build a small report showing useful graph intelligence questions."""

        top_technique = self._first_technique_with_recommendations()
        top_event = self._first_event_with_similar_incidents()
        return {
            "schema_version": "1.0",
            "questions": {
                "related_entities": self.find_related_entities(
                    top_technique.node_id if top_technique else ""
                ),
                "connected_weaknesses": self.find_connected_weaknesses(
                    top_technique.node_id if top_technique else ""
                ),
                "recommendations_for_technique": self.find_recommendations_for_technique(
                    top_technique.node_id if top_technique else ""
                ),
                "similar_incidents": self.find_similar_incidents(
                    top_event.node_id if top_event else ""
                ),
            },
        }

    def _related_entity(
        self,
        node_id: str,
        relationship_type: str,
        *,
        direction: str,
    ) -> dict[str, Any]:
        return {
            **self._node_result(node_id),
            "relationship_type": relationship_type,
            "direction": direction,
        }

    def _node_result(self, node_id: str) -> dict[str, Any]:
        node = self.graph.nodes[node_id]
        return {
            "id": node.node_id,
            "type": node.node_type,
            "label": node.label,
            "properties": node.properties,
        }

    def _first_node(self, node_type: str) -> Any:
        for node in sorted(self.graph.nodes.values(), key=lambda item: item.node_id):
            if node.node_type == node_type:
                return node
        return None

    def _first_technique_with_recommendations(self) -> Any:
        for node in sorted(self.graph.nodes.values(), key=lambda item: item.node_id):
            if node.node_type != "MITRE Technique":
                continue
            if self.find_recommendations_for_technique(node.node_id):
                return node
        return self._first_node("MITRE Technique")

    def _first_event_with_similar_incidents(self) -> Any:
        for node in sorted(self.graph.nodes.values(), key=lambda item: item.node_id):
            if node.node_type != "Event":
                continue
            if self.find_similar_incidents(node.node_id):
                return node
        return self._first_node("Event")

    def _normalize_entity_id(self, entity_id: str) -> str:
        if entity_id in self.graph.nodes:
            return entity_id
        if entity_id.startswith("T") and f"mitre:{entity_id}" in self.graph.nodes:
            return f"mitre:{entity_id}"
        if f"event:{entity_id}" in self.graph.nodes:
            return f"event:{entity_id}"
        return entity_id

    @staticmethod
    def _deduplicate_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[tuple[str, str, str], dict[str, Any]] = {}
        for entity in entities:
            key = (entity["id"], entity["relationship_type"], entity["direction"])
            unique[key] = entity
        return sorted(unique.values(), key=lambda item: (item["type"], item["id"]))


def load_graph(path: Path | str) -> KnowledgeGraph:
    """Load a KnowledgeGraph from the Phase 1 JSON graph artifact."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    graph = KnowledgeGraph()
    for node in payload.get("nodes", []):
        graph.add_node(
            str(node["id"]),
            str(node["type"]),
            str(node["label"]),
            dict(node.get("properties", {})),
        )
    for relationship in payload.get("relationships", []):
        graph.add_relationship(
            str(relationship["source"]),
            str(relationship["type"]),
            str(relationship["target"]),
            dict(relationship.get("properties", {})),
        )
    return graph


def write_sample_report(repository_root: Path | str = ".") -> dict[str, Any]:
    """Persist a sample graph intelligence output report."""

    root = Path(repository_root)
    intelligence = GraphIntelligence.from_repository(root)
    report = intelligence.sample_report()
    report_path = root / "reports" / "graph-intelligence-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report


def find_related_entities(entity_id: str, repository_root: Path | str = ".") -> list[dict[str, Any]]:
    return GraphIntelligence.from_repository(repository_root).find_related_entities(entity_id)


def find_connected_weaknesses(
    event_or_technique: str,
    repository_root: Path | str = ".",
) -> list[dict[str, Any]]:
    return GraphIntelligence.from_repository(repository_root).find_connected_weaknesses(
        event_or_technique
    )


def find_recommendations_for_technique(
    technique_id: str,
    repository_root: Path | str = ".",
) -> list[dict[str, Any]]:
    return GraphIntelligence.from_repository(repository_root).find_recommendations_for_technique(
        technique_id
    )


def find_similar_incidents(event_id: str, repository_root: Path | str = ".") -> list[dict[str, Any]]:
    return GraphIntelligence.from_repository(repository_root).find_similar_incidents(event_id)
