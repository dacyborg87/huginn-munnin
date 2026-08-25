"""Small JSON-backed knowledge graph for SOC intelligence artifacts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.json_persistence import atomic_write_json


NODE_TYPES = {
    "Event",
    "MITRE Technique",
    "Attack Chain",
    "Memory Entry",
    "Architecture Weakness",
    "Defense Recommendation",
}

RELATIONSHIP_TYPES = {
    "relates_to",
    "caused_by",
    "recommends",
    "previously_seen_as",
    "weakens",
}


@dataclass(frozen=True)
class KnowledgeNode:
    """A graph entity such as an event, technique, or recommendation."""

    node_id: str
    node_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "type": self.node_type,
            "label": self.label,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class KnowledgeRelationship:
    """A directional connection between two graph nodes."""

    source_id: str
    relationship_type: str
    target_id: str
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def relationship_id(self) -> str:
        return f"{self.source_id}:{self.relationship_type}:{self.target_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.relationship_id,
            "source": self.source_id,
            "type": self.relationship_type,
            "target": self.target_id,
            "properties": self.properties,
        }


class KnowledgeGraph:
    """In-memory graph with deterministic JSON persistence."""

    def __init__(self) -> None:
        self.nodes: dict[str, KnowledgeNode] = {}
        self.relationships: dict[str, KnowledgeRelationship] = {}

    def add_node(
        self,
        node_id: str,
        node_type: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> KnowledgeNode:
        if node_type not in NODE_TYPES:
            msg = f"Unsupported node type: {node_type}"
            raise ValueError(msg)

        existing = self.nodes.get(node_id)
        merged_properties = dict(existing.properties) if existing else {}
        merged_properties.update(properties or {})

        node = KnowledgeNode(
            node_id=node_id,
            node_type=node_type,
            label=label,
            properties=merged_properties,
        )
        self.nodes[node_id] = node
        return node

    def add_relationship(
        self,
        source_id: str,
        relationship_type: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
    ) -> KnowledgeRelationship:
        if relationship_type not in RELATIONSHIP_TYPES:
            msg = f"Unsupported relationship type: {relationship_type}"
            raise ValueError(msg)
        if source_id not in self.nodes:
            msg = f"Unknown source node: {source_id}"
            raise ValueError(msg)
        if target_id not in self.nodes:
            msg = f"Unknown target node: {target_id}"
            raise ValueError(msg)

        relationship = KnowledgeRelationship(
            source_id=source_id,
            relationship_type=relationship_type,
            target_id=target_id,
            properties=properties or {},
        )
        self.relationships[relationship.relationship_id] = relationship
        return relationship

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "nodes": [
                node.to_dict()
                for node in sorted(self.nodes.values(), key=lambda item: item.node_id)
            ],
            "relationships": [
                relationship.to_dict()
                for relationship in sorted(
                    self.relationships.values(),
                    key=lambda item: item.relationship_id,
                )
            ],
        }

    def save(self, path: Path | str) -> None:
        output_path = Path(path)
        atomic_write_json(output_path, self.to_dict())

    def summary(self, top_limit: int = 10) -> dict[str, Any]:
        connection_counts: Counter[str] = Counter()
        for relationship in self.relationships.values():
            connection_counts[relationship.source_id] += 1
            connection_counts[relationship.target_id] += 1

        top_connected = []
        for node_id, count in connection_counts.most_common(top_limit):
            node = self.nodes[node_id]
            top_connected.append(
                {
                    "id": node.node_id,
                    "type": node.node_type,
                    "label": node.label,
                    "connection_count": count,
                }
            )

        return {
            "schema_version": "1.0",
            "total_nodes": len(self.nodes),
            "total_relationships": len(self.relationships),
            "node_counts": dict(
                sorted(Counter(node.node_type for node in self.nodes.values()).items())
            ),
            "relationship_counts": dict(
                sorted(
                    Counter(
                        relationship.relationship_type
                        for relationship in self.relationships.values()
                    ).items()
                )
            ),
            "top_connected_entities": top_connected,
        }
