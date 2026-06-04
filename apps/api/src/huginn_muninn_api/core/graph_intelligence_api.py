"""Read-only API helpers for published graph intelligence JSON artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GraphIntelligenceApi:
    """Query existing graph JSON without importing repository-level core modules."""

    def __init__(self, repository_root: Path | str) -> None:
        self.repository_root = Path(repository_root)

    def summary(self) -> dict[str, Any]:
        summary_path = self.repository_root / "core" / "patterns" / "knowledge-graph-summary.json"
        if summary_path.exists():
            summary = self._read_json(summary_path, default={})
        else:
            graph = self._load_graph()
            summary = {
                "total_nodes": len(graph["nodes"]),
                "total_relationships": len(graph["relationships"]),
                "top_connected_entities": [],
            }
        return {
            "entity_searched": "knowledge_graph",
            "summary": summary,
            "connected_entities": summary.get("top_connected_entities", []),
            "weaknesses": [],
            "recommendations": [],
            "similar_incidents": [],
            "explanation": "This shows how many graph objects exist and which ones have the most connections.",
        }

    def related(self, entity_id: str) -> dict[str, Any]:
        graph = self._load_graph()
        normalized_id = self._normalize_entity_id(entity_id, graph["nodes"])
        related_entities = self._find_related_entities(normalized_id, graph)
        return {
            "entity_searched": entity_id,
            "normalized_entity": normalized_id,
            "connected_entities": related_entities,
            "weaknesses": [
                entity for entity in related_entities if entity["type"] == "Architecture Weakness"
            ],
            "recommendations": [
                entity for entity in related_entities if entity["type"] == "Defense Recommendation"
            ],
            "similar_incidents": [],
            "explanation": "This shows the graph objects directly connected to the searched entity.",
        }

    def weaknesses(self, entity_id: str) -> dict[str, Any]:
        graph = self._load_graph()
        normalized_id = self._normalize_entity_id(entity_id, graph["nodes"])
        weaknesses = self._find_connected_weaknesses(normalized_id, graph)
        return {
            "entity_searched": entity_id,
            "normalized_entity": normalized_id,
            "connected_entities": weaknesses,
            "weaknesses": weaknesses,
            "recommendations": [],
            "similar_incidents": [],
            "explanation": "This shows architecture weaknesses connected to the event or technique.",
        }

    def recommendations(self, technique_id: str) -> dict[str, Any]:
        graph = self._load_graph()
        normalized_id = self._normalize_entity_id(technique_id, graph["nodes"])
        weaknesses = self._find_connected_weaknesses(normalized_id, graph)
        weakness_ids = {weakness["id"] for weakness in weaknesses}
        recommendations = []
        for relationship in graph["relationships"]:
            if relationship["type"] != "recommends":
                continue
            if relationship["target"] not in weakness_ids:
                continue
            recommendation = graph["nodes"].get(relationship["source"])
            if recommendation and recommendation["type"] == "Defense Recommendation":
                recommendations.append(self._node_response(recommendation))
        return {
            "entity_searched": technique_id,
            "normalized_entity": normalized_id,
            "connected_entities": recommendations,
            "weaknesses": weaknesses,
            "recommendations": self._deduplicate(recommendations),
            "similar_incidents": [],
            "explanation": "This shows defense recommendations tied to weaknesses for the technique.",
        }

    def similar_incidents(self, event_id: str) -> dict[str, Any]:
        graph = self._load_graph()
        normalized_id = self._normalize_entity_id(event_id, graph["nodes"])
        similar_incidents = self._find_similar_incidents(normalized_id, graph)
        return {
            "entity_searched": event_id,
            "normalized_entity": normalized_id,
            "connected_entities": similar_incidents,
            "weaknesses": [],
            "recommendations": [],
            "similar_incidents": similar_incidents,
            "explanation": "This shows other events that share MITRE technique context with the searched event.",
        }

    def _load_graph(self) -> dict[str, Any]:
        graph_path = self.repository_root / "reports" / "knowledge-graph.json"
        payload = self._read_json(graph_path, default={"nodes": [], "relationships": []})
        return {
            "nodes": {str(node["id"]): node for node in payload.get("nodes", [])},
            "relationships": payload.get("relationships", []),
        }

    def _find_related_entities(self, entity_id: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
        related = []
        for relationship in graph["relationships"]:
            if relationship["source"] == entity_id:
                node = graph["nodes"].get(relationship["target"])
                if node:
                    related.append(
                        self._related_node_response(node, relationship["type"], "outgoing")
                    )
            elif relationship["target"] == entity_id:
                node = graph["nodes"].get(relationship["source"])
                if node:
                    related.append(
                        self._related_node_response(node, relationship["type"], "incoming")
                    )
        return self._deduplicate(related)

    def _find_connected_weaknesses(
        self,
        entity_id: str,
        graph: dict[str, Any],
    ) -> list[dict[str, Any]]:
        technique_ids = {entity_id} if entity_id.startswith("mitre:") else set()
        technique_ids.update(
            entity["id"]
            for entity in self._find_related_entities(entity_id, graph)
            if entity["type"] == "MITRE Technique"
        )

        weaknesses = []
        for relationship in graph["relationships"]:
            if relationship["type"] != "weakens":
                continue
            if relationship["target"] != entity_id and relationship["target"] not in technique_ids:
                continue
            node = graph["nodes"].get(relationship["source"])
            if node and node["type"] == "Architecture Weakness":
                weaknesses.append(self._node_response(node))
        return self._deduplicate(weaknesses)

    def _find_similar_incidents(self, event_id: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
        technique_ids = {
            entity["id"]
            for entity in self._find_related_entities(event_id, graph)
            if entity["type"] == "MITRE Technique"
        }
        incidents: dict[str, dict[str, Any]] = {}
        for relationship in graph["relationships"]:
            if relationship["type"] != "relates_to" or relationship["target"] not in technique_ids:
                continue
            node = graph["nodes"].get(relationship["source"])
            if not node or node["type"] != "Event" or node["id"] == event_id:
                continue
            incident = incidents.setdefault(
                node["id"],
                {
                    **self._node_response(node),
                    "shared_techniques": [],
                    "similarity_reason": "Shares MITRE technique context with the searched event.",
                },
            )
            technique = graph["nodes"].get(relationship["target"])
            if technique:
                incident["shared_techniques"].append(self._node_response(technique))
        return sorted(incidents.values(), key=lambda item: item["id"])

    @staticmethod
    def _normalize_entity_id(entity_id: str, nodes: dict[str, Any]) -> str:
        if entity_id in nodes:
            return entity_id
        if entity_id.startswith("T") and f"mitre:{entity_id}" in nodes:
            return f"mitre:{entity_id}"
        if f"event:{entity_id}" in nodes:
            return f"event:{entity_id}"
        return entity_id

    @staticmethod
    def _node_response(node: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": node["id"],
            "type": node["type"],
            "label": node["label"],
            "properties": node.get("properties", {}),
        }

    def _related_node_response(
        self,
        node: dict[str, Any],
        relationship_type: str,
        direction: str,
    ) -> dict[str, Any]:
        return {
            **self._node_response(node),
            "relationship_type": relationship_type,
            "direction": direction,
        }

    @staticmethod
    def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique = {item["id"]: item for item in items}
        return [unique[item_id] for item_id in sorted(unique)]

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
