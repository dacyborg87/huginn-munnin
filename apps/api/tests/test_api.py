from time import sleep

import pytest
from fastapi.testclient import TestClient

from core.outcome_tracker import OutcomeTracker
from core.reasoning_patterns import ReasoningPatternEngine
from huginn_muninn_api.main import app, orchestrator
from huginn_muninn_api.muninn.memory import MuninnMemory


@pytest.fixture(autouse=True)
def isolate_reasoning_patterns():
    # Fresh in-memory-backed instances per test. TestClient's lifespan also
    # rebinds fresh stores on every `with TestClient(app) as client:` entry
    # (see main.py), so this fixture and the lifespan startup are
    # complementary, not redundant: this covers direct orchestrator.*
    # attribute access before a client is opened, lifespan covers the
    # request path.
    orchestrator.muninn = MuninnMemory()
    orchestrator.outcome_tracker = OutcomeTracker()
    orchestrator.reasoning_patterns = ReasoningPatternEngine()


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
        assert response.json()["event_worker"]["available"] is True
        assert response.json()["database_readiness"] == "not_checked"


@pytest.mark.parametrize("state", ["not_started", "closing", "stopped", "failed"])
def test_event_submission_unavailable_returns_503(monkeypatch, state):
    from core.event_bus import EventBus
    from huginn_muninn_api import main

    with TestClient(app) as client:
        unavailable = EventBus()
        unavailable._state = state
        monkeypatch.setattr(main, "event_bus", unavailable)
        for path, payload in [
            ("/chat", {"message": "test"}),
            ("/memory", {"content": "must not be stored"}),
        ]:
            response = client.post(path, json=payload)
            assert response.status_code == 503
            assert response.json() == {"detail": "Event processing is unavailable"}
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json()["event_worker"]["state"] == state
        monkeypatch.undo()


def test_pool_cleanup_independent_of_worker_stop_failure(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from huginn_muninn_api import main

    async def run():
        pool = SimpleNamespace(close=AsyncMock(), terminate=Mock())
        stores = SimpleNamespace(
            pool=pool,
            system_log_store=object(),
            memory_store=object(),
            outcome_store=object(),
            pattern_store=object(),
        )
        monkeypatch.setattr(main, "build_stores", AsyncMock(return_value=stores))
        monkeypatch.setattr(
            main,
            "event_bus",
            SimpleNamespace(
                bind_log_store=Mock(),
                start=AsyncMock(),
                stop=AsyncMock(side_effect=RuntimeError("stop")),
            ),
        )
        monkeypatch.setattr(
            main,
            "orchestrator",
            SimpleNamespace(
                muninn=SimpleNamespace(bind_store=Mock()),
                outcome_tracker=SimpleNamespace(bind_store=Mock()),
                reasoning_patterns=SimpleNamespace(bind_store=Mock()),
                hydrate=AsyncMock(),
            ),
        )
        monkeypatch.setattr(
            main,
            "live_telemetry_api",
            SimpleNamespace(start_polling=AsyncMock(), stop_polling=AsyncMock()),
        )
        with pytest.raises(RuntimeError, match="stop"):
            async with main.lifespan(app):
                pass
        pool.close.assert_awaited_once()
        pool.terminate.assert_not_called()

    asyncio.run(run())


def test_pool_close_timeout_terminates_without_sensitive_logging(caplog):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import Mock

    from huginn_muninn_api import main

    async def run():
        cancelled = asyncio.Event()

        async def close():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        pool = SimpleNamespace(close=close, terminate=Mock())
        await asyncio.wait_for(main._close_pool(pool, 0.005), 0.5)
        pool.terminate.assert_called_once()
        await asyncio.wait_for(cancelled.wait(), 0.5)
        assert "stage=close result=timeout" in caplog.text

    asyncio.run(run())


def test_pool_close_failure_is_sanitized(caplog):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from huginn_muninn_api import main

    async def run():
        pool = SimpleNamespace(
            close=AsyncMock(side_effect=RuntimeError("SECRET_DSN")), terminate=Mock()
        )
        await main._close_pool(pool, 0.1)
        pool.terminate.assert_called_once()

    asyncio.run(run())
    assert "result=failed" in caplog.text
    assert "SECRET_DSN" not in caplog.text


def test_lifecycle_budget_environment(monkeypatch):
    from huginn_muninn_api import main

    monkeypatch.setenv("EVENT_DRAIN_TIMEOUT_SECONDS", "0.25")
    assert main._budget("EVENT_DRAIN_TIMEOUT_SECONDS", 5.0) == 0.25
    monkeypatch.setenv("EVENT_DRAIN_TIMEOUT_SECONDS", "nan")
    with pytest.raises(ValueError):
        main._budget("EVENT_DRAIN_TIMEOUT_SECONDS", 5.0)


def test_memory_round_trip() -> None:
    with TestClient(app) as client:
        record = {
            "content": "Project archive: built phase one memory scaffold.",
            "tags": ["project"],
        }
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


def test_memory_context_changes_branch_for_similar_command() -> None:
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
        orchestrator.reasoning_patterns = ReasoningPatternEngine()

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
            "/chat",
            json={"message": "Create incident report workflow draft", "namespace": namespace},
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
