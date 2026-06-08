import sys
from pathlib import Path

from fastapi.testclient import TestClient


API_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(API_SRC))
sys.modules.pop("core", None)

from huginn_muninn_api.main import app  # noqa: E402


def test_evidence_summary_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/evidence/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["entity_searched"] == "evidence"
    assert body["summary"]["total_records"] == 6
    assert body["match_count"] == 6
    assert body["evidence_records"]
    assert body["explanation"]


def test_evidence_finding_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/evidence/finding/weakness:15953a2c-3b98-4640-9401-1306f95162e3"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["query_type"] == "finding_id"
    assert body["match_count"] > 0
    assert any(
        record["source_reference"]
        == "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
        for record in body["evidence_records"]
    )
    assert body["explanation"]


def test_evidence_mitre_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/evidence/mitre/T1078")

    assert response.status_code == 200
    body = response.json()
    assert body["query_type"] == "mitre_technique"
    assert body["match_count"] > 0
    assert all(
        "mitre:T1078" in record["related_entities"]["mitre_techniques"]
        for record in body["evidence_records"]
    )


def test_evidence_weakness_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/evidence/weakness/15953a2c-3b98-4640-9401-1306f95162e3"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["query_type"] == "related_weakness"
    assert body["match_count"] > 0
    assert all(
        "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
        in record["related_entities"]["architecture_weaknesses"]
        or record["source_reference"]
        == "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
        for record in body["evidence_records"]
    )


def test_evidence_recommendation_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/evidence/recommendation/design.post_auth_telemetry_layer"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["query_type"] == "recommendation"
    assert body["match_count"] > 0
    assert all(
        "recommendation:design.post_auth_telemetry_layer"
        in record["related_entities"]["defense_recommendations"]
        or record["source_reference"]
        == "recommendation:design.post_auth_telemetry_layer"
        for record in body["evidence_records"]
    )


def test_evidence_confidence_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/evidence/confidence/high")

    assert response.status_code == 200
    body = response.json()
    assert body["query_type"] == "confidence_level"
    assert body["match_count"] == 6
    assert all(
        record["confidence"]["level"] == "high"
        for record in body["evidence_records"]
    )


def test_evidence_empty_result_is_clear() -> None:
    with TestClient(app) as client:
        response = client.get("/evidence/finding/finding:does-not-exist")

    assert response.status_code == 200
    body = response.json()
    assert body["match_count"] == 0
    assert body["evidence_records"] == []
    assert "No evidence records matched" in body["explanation"]
    assert "evidence gap" in body["explanation"]
