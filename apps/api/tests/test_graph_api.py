import sys
from pathlib import Path

from fastapi.testclient import TestClient


API_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(API_SRC))
sys.modules.pop("core", None)

from huginn_muninn_api.main import app  # noqa: E402


def test_graph_summary_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/graph/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "knowledge_graph"
    assert body["summary"]["total_nodes"] > 0
    assert body["connected_entities"]
    assert body["explanation"]


def test_graph_related_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/graph/related/mitre:T1078")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "mitre:T1078"
    assert body["connected_entities"]
    assert body["weaknesses"]
    assert body["explanation"]


def test_graph_weaknesses_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/graph/weaknesses/T1078")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "T1078"
    assert body["normalized_entity"] == "mitre:T1078"
    assert body["weaknesses"]
    assert all(weakness["type"] == "Architecture Weakness" for weakness in body["weaknesses"])


def test_graph_recommendations_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/graph/recommendations/T1078")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "T1078"
    assert body["recommendations"]
    assert any("post-auth" in recommendation["label"].lower() for recommendation in body["recommendations"])
    assert body["explanation"]


def test_graph_similar_incidents_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/graph/similar-incidents/f26fa03a-6c8e-44ca-b906-12c974dcbcbf")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "f26fa03a-6c8e-44ca-b906-12c974dcbcbf"
    assert body["normalized_entity"] == "event:f26fa03a-6c8e-44ca-b906-12c974dcbcbf"
    assert body["similar_incidents"]
    assert body["explanation"]
