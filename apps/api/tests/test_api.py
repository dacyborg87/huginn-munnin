from time import sleep

import pytest
from fastapi.testclient import TestClient

from core.outcome_tracker import OutcomeTracker
from core.reasoning_patterns import ReasoningPatternEngine
from huginn_muninn_api.muninn.memory import MuninnMemory
from huginn_muninn_api.main import app, orchestrator


@pytest.fixture(autouse=True)
def isolate_reasoning_patterns(tmp_path):
    orchestrator.muninn = MuninnMemory()
    orchestrator.outcome_tracker = OutcomeTracker()
    orchestrator.reasoning_patterns = ReasoningPatternEngine(
        storage_path=tmp_path / "reasoning_patterns.json"
    )


def event_types(client: TestClient) -> list[str]:
    response = client.get("/events")
    assert response.status_code == 200
    return [event["event_type"] for event in response.json()]


def events(client: TestClient) -> list[dict]:
    response = client.get("/events?limit=100")
    assert response.status_code == 200
    return response.json()


def selected_state_for_command(client: TestClient, command_event_id: str) -> str | None:
    for event in events(client):
        if (
            event["event_type"] == "AI_DECISION_MADE"
            and event["payload"]["command_event_id"] == command_event_id
        ):
            return event["payload"]["selected_state"]
    return None


def outcome_for_command(client: TestClient, command_event_id: str) -> dict | None:
    for event in events(client):
        if (
            event["event_type"] == "AI_OUTCOME_RECORDED"
            and event["payload"]["command_event_id"] == command_event_id
        ):
            return event["payload"]
    return None


def event_payload_for_command(
    client: TestClient, command_event_id: str, event_type: str
) -> dict | None:
    for event in events(client):
        if (
            event["event_type"] == event_type
            and event["payload"].get("command_event_id") == command_event_id
        ):
            return event["payload"]
    return None


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_memory_round_trip() -> None:
    with TestClient(app) as client:
        record = {"content": "Project archive: built phase one memory scaffold.", "tags": ["project"]}
        create_response = client.post("/memory", json=record)
        assert create_response.status_code == 200

        search_response = client.post("/memory/search", json={"query": "phase one"})
        assert search_response.status_code == 200
        assert len(search_response.json()) >= 1


def test_security_analysis() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/security/analyze",
            json={"content": "Wazuh alert: failed password followed by powershell -enc payload."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["severity"] == "high"
        assert "Credential Access" in body["mapped_tactics"]


def test_chat_accepts_command_and_runs_intelligence_graph() -> None:
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "Hey Huginn, analyze these logs."})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "accepted"
        assert body["event_id"]
        assert "response" not in body

        expected = {
            "USER_COMMAND_RECEIVED",
            "AI_CONTEXT_ENRICHED",
            "AI_THINKING_STARTED",
            "AI_DECISION_MADE",
            "AI_TASK_EXECUTING",
            "AI_TASK_COMPLETED",
            "MEMORY_WRITTEN",
            "AGENT_STATUS_UPDATED",
        }

        observed: set[str] = set()
        for _ in range(20):
            observed = set(event_types(client))
            if expected.issubset(observed):
                break
            sleep(0.05)

        assert expected.issubset(observed)
        assert selected_state_for_command(client, body["event_id"]) == "TOOL_USE"


def test_chat_emits_enriched_intelligence_context() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/chat",
            json={"message": "Hey Huginn, investigate T1078 valid account activity."},
        )
        assert response.status_code == 200
        command_event_id = response.json()["event_id"]

        context_payload: dict | None = None
        for _ in range(20):
            context_payload = event_payload_for_command(
                client, command_event_id, "AI_CONTEXT_ENRICHED"
            )
            if context_payload is not None:
                break
            sleep(0.05)

        assert context_payload is not None
        intelligence_context = context_payload["intelligence_context"]
        assert intelligence_context["summary"]["entity_searched"] == "knowledge_graph"
        assert intelligence_context["detected_entities"] == ["T1078"]
        assert intelligence_context["related_entities"]["T1078"]["connected_entities"]


def test_memory_context_changes_branch_for_similar_command(tmp_path) -> None:
    namespace = "branching-test"
    message = "Continue project work"

    with TestClient(app) as client:
        first_response = client.post("/chat", json={"message": message, "namespace": namespace})
        assert first_response.status_code == 200
        first_command_id = first_response.json()["event_id"]

        first_state: str | None = None
        for _ in range(20):
            first_state = selected_state_for_command(client, first_command_id)
            if first_state is not None:
                break
            sleep(0.05)

        assert first_state == "PLANNING"
        orchestrator.reasoning_patterns = ReasoningPatternEngine(
            storage_path=tmp_path / "memory_branch_patterns.json"
        )

        memory_response = client.post(
            "/memory",
            json={
                "namespace": namespace,
                "content": "Continue project work from saved Muninn project context.",
                "tags": ["continue", "project", "work"],
            },
        )
        assert memory_response.status_code == 200

        second_response = client.post("/chat", json={"message": message, "namespace": namespace})
        assert second_response.status_code == 200
        second_command_id = second_response.json()["event_id"]

        second_state: str | None = None
        for _ in range(20):
            second_state = selected_state_for_command(client, second_command_id)
            if second_state is not None:
                break
            sleep(0.05)

        assert second_state == "MEMORY_LOOKUP"


def test_failed_outcome_changes_future_routing_for_same_command() -> None:
    namespace = "learning-test"
    message = "simulate failure analyze logs"

    with TestClient(app) as client:
        first_response = client.post("/chat", json={"message": message, "namespace": namespace})
        assert first_response.status_code == 200
        first_command_id = first_response.json()["event_id"]

        first_state: str | None = None
        first_outcome: dict | None = None
        for _ in range(20):
            first_state = selected_state_for_command(client, first_command_id)
            first_outcome = outcome_for_command(client, first_command_id)
            if first_state is not None and first_outcome is not None:
                break
            sleep(0.05)

        assert first_state == "TOOL_USE"
        assert first_outcome is not None
        assert first_outcome["result"] == "failure"
        assert first_outcome["updated_weights"]["TOOL_USE"] < 0

        second_response = client.post("/chat", json={"message": message, "namespace": namespace})
        assert second_response.status_code == 200
        second_command_id = second_response.json()["event_id"]

        second_state: str | None = None
        for _ in range(20):
            second_state = selected_state_for_command(client, second_command_id)
            if second_state is not None:
                break
            sleep(0.05)

        assert second_state == "PLANNING"


def test_reasoning_patterns_are_recorded_and_influence_similar_contexts() -> None:
    namespace = "pattern-test"
    message = "Create incident report workflow"

    with TestClient(app) as client:
        first_response = client.post("/chat", json={"message": message, "namespace": namespace})
        first_command_id = first_response.json()["event_id"]

        first_pattern: dict | None = None
        for _ in range(20):
            first_pattern = event_payload_for_command(
                client, first_command_id, "AI_PATTERN_RECORDED"
            )
            if first_pattern is not None:
                break
            sleep(0.05)

        assert first_pattern is not None
        assert first_pattern["success_rate"] >= 0

        second_response = client.post(
            "/chat", json={"message": "Create incident report workflow draft", "namespace": namespace}
        )
        second_command_id = second_response.json()["event_id"]

        second_decision: dict | None = None
        pattern_lookup: dict | None = None
        for _ in range(20):
            second_decision = event_payload_for_command(
                client, second_command_id, "AI_DECISION_MADE"
            )
            pattern_lookup = event_payload_for_command(
                client, second_command_id, "PATTERN_MATCH_LOOKUP"
            )
            if second_decision is not None and pattern_lookup is not None:
                break
            sleep(0.05)

        assert second_decision is not None
        assert pattern_lookup is not None
        assert pattern_lookup["matched_patterns"]
        assert any(value > 0 for value in second_decision["pattern_influence"].values())
        assert "Reasoning patterns add" in second_decision["reasoning"]
