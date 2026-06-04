"""Build the Phase 1 Munnin knowledge graph from existing JSON reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.knowledge_graph import KnowledgeGraph


class GraphContextBuilder:
    """Create a simple graph from report and memory artifacts."""

    def __init__(self, repository_root: Path | str = ".") -> None:
        self.repository_root = Path(repository_root)

    def build(self, persist: bool = True) -> KnowledgeGraph:
        graph = KnowledgeGraph()
        self._add_events(graph)
        self._add_attack_chains(graph)
        self._add_memory_entries(graph)
        self._add_architecture_weaknesses(graph)
        self._add_defense_recommendations(graph)

        if persist:
            self.persist(graph)

        return graph

    def persist(self, graph: KnowledgeGraph) -> None:
        graph_path = self.repository_root / "reports" / "knowledge-graph.json"
        summary_path = (
            self.repository_root / "core" / "patterns" / "knowledge-graph-summary.json"
        )
        graph.save(graph_path)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(graph.summary(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _add_events(self, graph: KnowledgeGraph) -> None:
        for event in self._read_jsonl(self.repository_root / "reports" / "soc-events.jsonl"):
            event_id = str(event.get("event_id", ""))
            if not event_id:
                continue
            event_node_id = self._event_node_id(event_id)
            graph.add_node(
                event_node_id,
                "Event",
                str(event.get("event_type", "event")),
                {
                    "source_system": event.get("source_system", ""),
                    "severity": event.get("severity", ""),
                    "timestamp": event.get("timestamp", ""),
                    "normalized_context": event.get("normalized_context", {}),
                },
            )

            for mapping in event.get("mitre_mapping", []):
                technique_id = str(mapping.get("technique_id", ""))
                if not technique_id:
                    continue
                technique_node_id = self._technique_node_id(technique_id)
                graph.add_node(
                    technique_node_id,
                    "MITRE Technique",
                    self._technique_label(technique_id, mapping.get("technique_name", "")),
                    {
                        "technique_id": technique_id,
                        "technique_name": mapping.get("technique_name", ""),
                        "tactic": mapping.get("tactic", ""),
                    },
                )
                graph.add_relationship(event_node_id, "relates_to", technique_node_id)

    def _add_attack_chains(self, graph: KnowledgeGraph) -> None:
        chains = self._read_json(
            self.repository_root / "reports" / "attack-chain-analysis.json",
            default=[],
        )
        for chain in chains:
            chain_id = str(chain.get("chain_id", "unknown-chain"))
            chain_node_id = self._attack_chain_node_id(chain_id)
            graph.add_node(
                chain_node_id,
                "Attack Chain",
                chain_id,
                {
                    "chain_severity": chain.get("chain_severity", ""),
                    "phase_sequence": chain.get("phase_sequence", []),
                    "technique_sequence": chain.get("technique_sequence", []),
                    "undetected_techniques": chain.get("undetected_techniques", []),
                },
            )

            for step in chain.get("steps", []):
                event_id = str(step.get("event_id", ""))
                technique_id = str(step.get("technique_id", ""))
                if event_id:
                    event_node_id = self._event_node_id(event_id)
                    if event_node_id not in graph.nodes:
                        graph.add_node(
                            event_node_id,
                            "Event",
                            str(step.get("event_type", "chain_step")),
                            {
                                "phase": step.get("phase", ""),
                                "timestamp": step.get("timestamp", ""),
                            },
                        )
                    graph.add_relationship(chain_node_id, "relates_to", event_node_id)

                if technique_id:
                    technique_node_id = self._technique_node_id(technique_id)
                    if technique_node_id not in graph.nodes:
                        graph.add_node(
                            technique_node_id,
                            "MITRE Technique",
                            self._technique_label(
                                technique_id,
                                str(step.get("technique_name", "")),
                            ),
                            {
                                "technique_id": technique_id,
                                "technique_name": step.get("technique_name", ""),
                                "tactic": step.get("tactic", ""),
                            },
                        )
                    graph.add_relationship(chain_node_id, "relates_to", technique_node_id)

            for transition in chain.get("missing_transitions", []):
                from_id = str(transition.get("from_technique", ""))
                to_id = str(transition.get("to_technique", ""))
                if from_id and to_id:
                    graph.add_relationship(
                        self._technique_node_id(to_id),
                        "caused_by",
                        self._technique_node_id(from_id),
                        {
                            "reason": transition.get("reason", ""),
                            "from_phase": transition.get("from_phase", ""),
                            "to_phase": transition.get("to_phase", ""),
                            "detected_transition": transition.get("detected_transition", False),
                        },
                    )

    def _add_memory_entries(self, graph: KnowledgeGraph) -> None:
        entries = self._read_json(
            self.repository_root / "core" / "patterns" / "strategic-memory.json",
            default=[],
        )
        for entry in entries:
            pattern_id = str(entry.get("pattern_id", ""))
            if not pattern_id:
                continue
            memory_node_id = self._memory_node_id(pattern_id)
            graph.add_node(
                memory_node_id,
                "Memory Entry",
                str(entry.get("key", pattern_id)),
                {
                    "pattern_type": entry.get("pattern_type", ""),
                    "occurrence_count": entry.get("occurrence_count", 0),
                    "failure_modes": entry.get("failure_modes", []),
                    "recommended_focus": entry.get("recommended_focus", ""),
                    "status": entry.get("status", ""),
                },
            )

            for chain_id in entry.get("related_chains", []):
                chain_node_id = self._attack_chain_node_id(str(chain_id))
                if chain_node_id in graph.nodes:
                    graph.add_relationship(memory_node_id, "previously_seen_as", chain_node_id)

            for technique_id in entry.get("related_techniques", []):
                technique_node_id = self._technique_node_id(str(technique_id))
                if technique_node_id in graph.nodes:
                    graph.add_relationship(memory_node_id, "previously_seen_as", technique_node_id)

    def _add_architecture_weaknesses(self, graph: KnowledgeGraph) -> None:
        weaknesses = self._read_json(
            self.repository_root / "reports" / "security-architecture-weaknesses.json",
            default=[],
        )
        for weakness in weaknesses:
            weakness_id = str(weakness.get("weakness_id", ""))
            if not weakness_id:
                continue
            weakness_node_id = self._weakness_node_id(weakness_id)
            graph.add_node(
                weakness_node_id,
                "Architecture Weakness",
                str(weakness.get("title", weakness_id)),
                {
                    "weakness_type": weakness.get("weakness_type", ""),
                    "affected_layer": weakness.get("affected_layer", ""),
                    "severity": weakness.get("severity", ""),
                    "architectural_impact": weakness.get("architectural_impact", ""),
                    "status": weakness.get("status", ""),
                },
            )

            evidence = weakness.get("evidence", {})
            for technique_id in evidence.get("undetected_post_auth_techniques", []):
                technique_node_id = self._technique_node_id(str(technique_id))
                if technique_node_id in graph.nodes:
                    graph.add_relationship(weakness_node_id, "weakens", technique_node_id)

            for technique_id in evidence.get("weak_response_techniques", []):
                technique_node_id = self._technique_node_id(str(technique_id))
                if technique_node_id in graph.nodes:
                    graph.add_relationship(weakness_node_id, "weakens", technique_node_id)

            for chain_id in evidence.get("chains_with_post_auth_misses", []):
                chain_node_id = self._attack_chain_node_id(str(chain_id))
                if chain_node_id in graph.nodes:
                    graph.add_relationship(weakness_node_id, "weakens", chain_node_id)

            for transition in evidence.get("missing_transitions", []):
                for field_name in ("from_technique", "to_technique"):
                    technique_node_id = self._technique_node_id(str(transition.get(field_name, "")))
                    if technique_node_id in graph.nodes:
                        graph.add_relationship(
                            weakness_node_id,
                            "weakens",
                            technique_node_id,
                            {"transition_context": transition},
                        )

            for pattern_id in evidence.get("strategic_memory_patterns", []):
                memory_node_id = self._memory_node_id(str(pattern_id))
                if memory_node_id in graph.nodes:
                    graph.add_relationship(weakness_node_id, "caused_by", memory_node_id)

    def _add_defense_recommendations(self, graph: KnowledgeGraph) -> None:
        recommendations = self._read_json(
            self.repository_root / "reports" / "defense-design-recommendations.json",
            default=[],
        )
        for recommendation in recommendations:
            recommendation_id = str(recommendation.get("recommendation_id", ""))
            if not recommendation_id:
                continue
            recommendation_node_id = self._recommendation_node_id(recommendation_id)
            graph.add_node(
                recommendation_node_id,
                "Defense Recommendation",
                str(recommendation.get("title", recommendation_id)),
                {
                    "design_area": recommendation.get("design_area", ""),
                    "recommended_subsystem": recommendation.get("recommended_subsystem", ""),
                    "architectural_change": recommendation.get("architectural_change", ""),
                    "expected_outcome": recommendation.get("expected_outcome", ""),
                    "status": recommendation.get("status", ""),
                },
            )

            design_area = str(recommendation.get("design_area", ""))
            subsystem = str(recommendation.get("recommended_subsystem", ""))
            for weakness in graph.nodes.values():
                if weakness.node_type != "Architecture Weakness":
                    continue
                affected_layer = str(weakness.properties.get("affected_layer", ""))
                weakness_type = str(weakness.properties.get("weakness_type", ""))
                if self._recommendation_matches_weakness(design_area, subsystem, affected_layer, weakness_type):
                    graph.add_relationship(recommendation_node_id, "recommends", weakness.node_id)

    @staticmethod
    def _recommendation_matches_weakness(
        design_area: str,
        subsystem: str,
        affected_layer: str,
        weakness_type: str,
    ) -> bool:
        searchable = f"{design_area} {subsystem}".replace("_", " ").replace("-", " ").lower()
        layer = affected_layer.replace("-", " ").lower()
        weakness = weakness_type.replace("_", " ").lower()
        return bool(layer and layer in searchable) or any(
            token in searchable for token in weakness.split() if len(token) > 4
        )

    @staticmethod
    def _event_node_id(event_id: str) -> str:
        return f"event:{event_id}"

    @staticmethod
    def _technique_node_id(technique_id: str) -> str:
        return f"mitre:{technique_id}"

    @staticmethod
    def _attack_chain_node_id(chain_id: str) -> str:
        return f"attack-chain:{chain_id}"

    @staticmethod
    def _memory_node_id(pattern_id: str) -> str:
        return f"memory:{pattern_id}"

    @staticmethod
    def _weakness_node_id(weakness_id: str) -> str:
        return f"weakness:{weakness_id}"

    @staticmethod
    def _recommendation_node_id(recommendation_id: str) -> str:
        return f"recommendation:{recommendation_id}"

    @staticmethod
    def _technique_label(technique_id: str, technique_name: Any) -> str:
        if technique_name:
            return f"{technique_id} {technique_name}"
        return technique_id

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []

        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records
