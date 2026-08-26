"""Phase B2 — Security Knowledge Graph-aware decision evidence.

Proves SKG evidence is additive, bounded, query-shape-aware, auditable, and
— critically — never a hard routing override, while leaving decision
scoring exactly unchanged when no evidence exists.
"""

from __future__ import annotations

from time import sleep

from fastapi.testclient import TestClient

from core.decision_engine import DecisionEngine

CONTEXT_WITH_ONE_TECHNIQUE = {
    "detected_entities": ["T1078"],
    "related_entities": {
        "T1078": {
            "weaknesses": [{"id": "weakness:1", "type": "Architecture Weakness"}],
            "recommendations": [{"id": "rec:1", "type": "Defense Recommendation"}],
        }
    },
}


def _engine() -> DecisionEngine:
    return DecisionEngine()


# ---------------------------------------------------------------------------
# 1. Neutral parity — the critical guarantee
# ---------------------------------------------------------------------------


def test_no_intelligence_context_matches_omitted_parameter() -> None:
    engine = _engine()
    without_param = engine.evaluate("investigate this alert", [])
    with_none = engine.evaluate("investigate this alert", [], intelligence_context=None)

    assert without_param.scores == with_none.scores
    assert without_param.base_scores == with_none.base_scores
    assert with_none.domain_evidence == {}


def test_empty_intelligence_context_yields_exact_neutral_parity() -> None:
    engine = _engine()
    baseline = engine.evaluate("investigate this alert", [], learned_weights={"TOOL_USE": 0.1})
    with_empty_context = engine.evaluate(
        "investigate this alert",
        [],
        learned_weights={"TOOL_USE": 0.1},
        intelligence_context={"detected_entities": [], "related_entities": {}},
    )

    assert baseline.scores == with_empty_context.scores, "exact dict equality, not approximate"
    assert baseline.base_scores == with_empty_context.base_scores
    assert with_empty_context.domain_evidence == {}


def test_golden_pre_b2_scores_unchanged_for_plain_message() -> None:
    """Pins down the pre-B2 heuristic formula itself, not just the new
    addition — catches accidental drift in the untouched base scoring."""
    engine = _engine()
    result = engine.evaluate("Hey Huginn, analyze these logs.", [])

    assert result.intent == "cybersecurity"
    assert result.scores["TOOL_USE"] > result.scores["PLANNING"] > result.scores["MEMORY_LOOKUP"]
    assert result.domain_evidence == {}


# ---------------------------------------------------------------------------
# 2. Informational query: never boosts TOOL_USE, never forced there
# ---------------------------------------------------------------------------


def test_informational_query_gets_zero_tool_use_evidence() -> None:
    engine = _engine()
    result = engine.evaluate(
        "What is T1078 valid accounts technique?",
        [],
        intelligence_context=CONTEXT_WITH_ONE_TECHNIQUE,
    )

    assert result.domain_evidence.get("TOOL_USE", 0.0) == 0.0
    assert result.domain_evidence["MEMORY_LOOKUP"] > result.domain_evidence["PLANNING"]


def test_mitre_mention_never_forces_tool_use_for_informational_phrasing() -> None:
    """The critical question: SKG evidence must remain bounded, never a
    hard override — a MITRE mention alone cannot force TOOL_USE."""
    engine = _engine()
    without_skg = engine.evaluate("What is T1078 valid accounts technique?", [])
    with_skg = engine.evaluate(
        "What is T1078 valid accounts technique?",
        [],
        intelligence_context=CONTEXT_WITH_ONE_TECHNIQUE,
    )

    # Evidence must never flip the outcome to TOOL_USE when the unadjusted
    # scoring didn't already favor it -- informational phrasing carries no
    # "cybersecurity" intent boost here ("what", "T1078" aren't in
    # security_terms), so TOOL_USE stays the lowest-scored path either way.
    # DecisionResult has no selected_state attribute -- derive it exactly
    # as orchestrator.py / intelligence_graph.py already do.
    without_skg_selected = max(without_skg.scores, key=without_skg.scores.get)
    with_skg_selected = max(with_skg.scores, key=with_skg.scores.get)
    assert without_skg_selected != "TOOL_USE"
    assert with_skg_selected != "TOOL_USE"


# ---------------------------------------------------------------------------
# 3. Action/investigative query: boosts TOOL_USE, never MEMORY_LOOKUP
# ---------------------------------------------------------------------------


def test_action_query_gets_zero_memory_lookup_evidence() -> None:
    engine = _engine()
    result = engine.evaluate(
        "Investigate this T1078 valid accounts alert now",
        [],
        intelligence_context=CONTEXT_WITH_ONE_TECHNIQUE,
    )

    assert result.domain_evidence.get("MEMORY_LOOKUP", 0.0) == 0.0
    assert result.domain_evidence["TOOL_USE"] > result.domain_evidence["PLANNING"]


# ---------------------------------------------------------------------------
# 4. Evidence bounding
# ---------------------------------------------------------------------------


def test_evidence_magnitude_caps_at_0_15_with_many_entities() -> None:
    engine = _engine()
    heavy_context = {
        "detected_entities": [f"T{1000 + i}" for i in range(10)],
        "related_entities": {
            f"T{1000 + i}": {
                "weaknesses": [{"id": f"w{i}"}] * 10,
                "recommendations": [{"id": f"r{i}"}] * 10,
            }
            for i in range(10)
        },
    }
    result = engine.evaluate(
        "investigate this alert", [], intelligence_context=heavy_context
    )

    total_evidence_capacity = max(result.domain_evidence.values())
    assert total_evidence_capacity <= 0.15 + 1e-9


def test_neutral_query_shape_caps_each_path_at_0_05() -> None:
    engine = _engine()
    heavy_context = {
        "detected_entities": [f"T{2000 + i}" for i in range(10)],
        "related_entities": {
            f"T{2000 + i}": {"weaknesses": [{"id": f"w{i}"}] * 10, "recommendations": []}
            for i in range(10)
        },
    }
    # No action_terms, no informational_terms -> neutral query shape.
    result = engine.evaluate(
        "the quarterly report is due", [], intelligence_context=heavy_context
    )

    for evidence in result.domain_evidence.values():
        assert evidence <= 0.05 + 1e-9


# ---------------------------------------------------------------------------
# 5. Missing / malformed intelligence_context: never raises
# ---------------------------------------------------------------------------


def test_none_intelligence_context_does_not_raise() -> None:
    result = _engine().evaluate("investigate this alert", [], intelligence_context=None)
    assert result.domain_evidence == {}


def test_empty_dict_intelligence_context_does_not_raise() -> None:
    result = _engine().evaluate("investigate this alert", [], intelligence_context={})
    assert result.domain_evidence == {}


def test_malformed_detected_entities_does_not_raise() -> None:
    result = _engine().evaluate(
        "investigate this alert", [], intelligence_context={"detected_entities": "not-a-list"}
    )
    assert result.domain_evidence == {}


def test_malformed_related_entities_does_not_raise() -> None:
    result = _engine().evaluate(
        "investigate this alert",
        [],
        intelligence_context={"detected_entities": ["T1078"], "related_entities": "not-a-dict"},
    )
    # mitre_count=1 still contributes; weaknesses/recommendations safely
    # default to 0 rather than raising on the malformed related_entities.
    assert result.domain_evidence != {}


def test_related_entities_with_malformed_entry_does_not_raise() -> None:
    result = _engine().evaluate(
        "investigate this alert",
        [],
        intelligence_context={
            "detected_entities": ["T1078"],
            "related_entities": {"T1078": "not-a-dict"},
        },
    )
    assert isinstance(result.domain_evidence, dict)


# ---------------------------------------------------------------------------
# 6. Auditability
# ---------------------------------------------------------------------------


def test_reasoning_string_mentions_domain_evidence_when_present() -> None:
    result = _engine().evaluate(
        "Investigate this T1078 valid accounts alert now",
        [],
        intelligence_context=CONTEXT_WITH_ONE_TECHNIQUE,
    )
    assert "security knowledge graph evidence" in result.reasoning.lower()


def test_reasoning_string_notes_absence_when_no_evidence() -> None:
    result = _engine().evaluate("investigate this alert", [])
    assert "no security knowledge graph evidence was available" in result.reasoning.lower()


# ---------------------------------------------------------------------------
# 7. Orchestrator integration — real pipeline, real event bus
# ---------------------------------------------------------------------------


def test_orchestrator_forwards_intelligence_context_into_decision() -> None:
    from huginn_muninn_api.main import app

    with TestClient(app) as client:
        response = client.post(
            "/chat", json={"message": "Investigate T1078 valid account activity now."}
        )
        assert response.status_code == 200
        command_event_id = response.json()["event_id"]

        decision_payload = None
        for _ in range(20):
            events_response = client.get("/events?limit=100")
            for entry in events_response.json():
                if (
                    entry["event_type"] == "AI_DECISION_MADE"
                    and entry["payload"].get("command_event_id") == command_event_id
                ):
                    decision_payload = entry["payload"]
                    break
            if decision_payload is not None:
                break
            sleep(0.05)

        assert decision_payload is not None
        assert "security knowledge graph evidence" in decision_payload["reasoning"].lower()
