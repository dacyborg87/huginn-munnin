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
from core.graph_intelligence import GraphIntelligence  # noqa: E402


def intelligence() -> GraphIntelligence:
    return GraphIntelligence(GraphContextBuilder(REPOSITORY_ROOT).build(persist=False))


def test_find_related_entities_returns_direct_neighbors() -> None:
    related = intelligence().find_related_entities("mitre:T1078")

    assert related
    assert any(entity["type"] == "Attack Chain" for entity in related)
    assert any(entity["type"] == "Architecture Weakness" for entity in related)


def test_find_connected_weaknesses_for_technique() -> None:
    weaknesses = intelligence().find_connected_weaknesses("T1078")

    assert weaknesses
    assert all(weakness["type"] == "Architecture Weakness" for weakness in weaknesses)
    assert any("post-auth" in weakness["label"].lower() for weakness in weaknesses)


def test_find_connected_weaknesses_for_event() -> None:
    weaknesses = intelligence().find_connected_weaknesses(
        "event:64ef7517-c6bf-419f-99d1-2c6d93984694"
    )

    assert weaknesses
    assert any(weakness["type"] == "Architecture Weakness" for weakness in weaknesses)


def test_find_recommendations_for_technique() -> None:
    recommendations = intelligence().find_recommendations_for_technique("T1078")

    assert recommendations
    assert all(
        recommendation["type"] == "Defense Recommendation"
        for recommendation in recommendations
    )
    assert any("post-auth" in recommendation["label"].lower() for recommendation in recommendations)


def test_find_similar_incidents() -> None:
    similar = intelligence().find_similar_incidents(
        "event:f26fa03a-6c8e-44ca-b906-12c974dcbcbf"
    )

    assert similar
    assert all(incident["type"] == "Event" for incident in similar)
    assert any(
        incident["id"] == "event:d2fe3656-5e49-472e-ab56-57f500cf4bd4"
        for incident in similar
    )
    assert all(incident["shared_techniques"] for incident in similar)


def test_sample_report_contains_all_phase_two_questions() -> None:
    report = intelligence().sample_report()

    assert set(report["questions"]) == {
        "related_entities",
        "connected_weaknesses",
        "recommendations_for_technique",
        "similar_incidents",
    }
