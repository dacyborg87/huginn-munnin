import sys
import types
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPOSITORY_ROOT / "apps" / "api" / "src"
if str(API_SRC) in sys.path:
    sys.path.remove(str(API_SRC))
sys.path.insert(0, str(REPOSITORY_ROOT))
core_package = types.ModuleType("core")
core_package.__path__ = [str(REPOSITORY_ROOT / "core")]
sys.modules["core"] = core_package

from core.graph_context_builder import GraphContextBuilder  # noqa: E402
from core.knowledge_graph import KnowledgeGraph  # noqa: E402


def test_knowledge_graph_accepts_required_node_and_relationship_types() -> None:
    graph = KnowledgeGraph()
    graph.add_node("event:1", "Event", "detection.alert")
    graph.add_node("mitre:T1110", "MITRE Technique", "T1110 Brute Force")
    graph.add_relationship("event:1", "relates_to", "mitre:T1110")

    summary = graph.summary()

    assert summary["total_nodes"] == 2
    assert summary["total_relationships"] == 1
    assert summary["top_connected_entities"][0]["connection_count"] == 1


def test_graph_context_builder_generates_sample_graph_from_reports() -> None:
    graph = GraphContextBuilder().build(persist=False)
    summary = graph.summary()

    assert summary["total_nodes"] > 0
    assert summary["total_relationships"] > 0
    assert summary["node_counts"]["MITRE Technique"] >= 1
    assert summary["node_counts"]["Attack Chain"] >= 1
    assert summary["node_counts"]["Memory Entry"] >= 1
    assert summary["node_counts"]["Architecture Weakness"] >= 1
    assert summary["node_counts"]["Defense Recommendation"] >= 1
    assert any(
        relationship.relationship_type == "recommends"
        for relationship in graph.relationships.values()
    )
