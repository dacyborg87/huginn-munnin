"""Cross-subsystem integration: real ingest -> persistent SKG/evidence ->
GraphIntelligenceApi -> IntelligenceContextBuilder -> DecisionEngine.

Every other test in this suite stops at one link in that chain: the
ingestion-persistence tests prove the write side, the intelligence-context
tests prove regex/graph-lookup behavior against a pre-existing static graph,
and the Phase B2 decision tests prove scoring behavior against a hand-built
`intelligence_context` fixture. Nothing proves the whole chain is actually
connected end to end. This file owns exactly that boundary.

Uses a temporary repository root throughout (via the same
`shutil.copytree(core/, tmp_path/core)` pattern `test_ingest_persistence.py`
already established) so nothing here ever touches the real repository's
`reports/` artifacts.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

API_SRC = Path(__file__).resolve().parents[1] / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

from core.decision_engine import DecisionEngine  # noqa: E402
from huginn_muninn_api.core.graph_intelligence_api import GraphIntelligenceApi  # noqa: E402
from huginn_muninn_api.core.guardduty_ingest_api import GuardDutyIngestApi  # noqa: E402
from huginn_muninn_api.core.intelligence_context import IntelligenceContextBuilder  # noqa: E402
from huginn_muninn_api.core.wazuh_ingest_api import WazuhIngestApi  # noqa: E402


def _temp_repository(tmp_path: Path) -> Path:
    """Isolated repository root: a real copy of core/ (so the ingest APIs'
    internal dynamic module loading has real files to load) plus an empty
    reports/ directory. Never the developer's actual repository."""
    shutil.copytree(REPOSITORY_ROOT / "core", tmp_path / "core")
    (tmp_path / "reports").mkdir()
    (tmp_path / "core" / "patterns").mkdir(exist_ok=True)
    return tmp_path


def _wazuh_alert(alert_id: str, technique_id: str) -> dict[str, Any]:
    return {
        "id": alert_id,
        "timestamp": "2026-06-17T12:00:00.000Z",
        "agent": {"name": "windows-endpoint-01"},
        "rule": {
            "id": "60199",
            "level": 10,
            "description": "Sustained endpoint resource exhaustion",
            "mitre": {"id": [technique_id]},
        },
    }


def _guardduty_finding(finding_id: str) -> dict[str, Any]:
    # AwsGuardDutyParser maps this exact finding type to MITRE T1071
    # (Application Layer Protocol / C2) — the same mapping
    # test_ingest_persistence.py's own GuardDuty fixture relies on.
    return {
        "id": finding_id,
        "type": "Trojan:EC2/BlackholeTraffic",
        "title": "EC2 instance communicating with known black hole IP",
        "severity": 8.0,
        "createdAt": "2026-06-17T00:00:00Z",
        "updatedAt": "2026-06-17T00:01:00Z",
        "resource": {
            "resourceType": "Instance",
            "instanceDetails": {"instanceId": "i-0synthetic123"},
        },
    }


def _assert_pipeline_reaches_decision_engine(
    repository_root: Path,
    *,
    event_node_id: str,
    evidence_id: str,
    technique_id: str,
) -> None:
    """The four-link proof, shared by every ingestion source this file
    exercises. Each assertion names the boundary it verifies, so a failure
    here immediately identifies which link broke."""

    # --- Assertion 1: persistence ---
    graph = json.loads(
        (repository_root / "reports" / "knowledge-graph.json").read_text(encoding="utf-8")
    )
    node_ids = {node["id"] for node in graph["nodes"]}
    assert event_node_id in node_ids, "ingest did not persist the event node to knowledge-graph.json"
    assert f"mitre:{technique_id}" in node_ids, "ingest did not persist the technique node"

    evidence = json.loads(
        (repository_root / "reports" / "evidence-index.json").read_text(encoding="utf-8")
    )
    evidence_ids = {record["evidence_id"] for record in evidence["evidence"]}
    assert evidence_id in evidence_ids, "ingest did not persist the evidence record"

    # --- Assertion 2: GraphIntelligenceApi (real read-after-write) ---
    related = GraphIntelligenceApi(repository_root).related(f"mitre:{technique_id}")
    related_entity_ids = {entity["id"] for entity in related["connected_entities"]}
    assert event_node_id in related_entity_ids, (
        "GraphIntelligenceApi.related() does not see the freshly-ingested event "
        "-- persistence and the production read path have diverged"
    )

    # --- Assertion 3: IntelligenceContextBuilder (bridge layer) ---
    message = f"Investigate {technique_id} now"
    context = IntelligenceContextBuilder(repository_root).build(message)
    assert technique_id in context["detected_entities"], (
        "IntelligenceContextBuilder failed to detect the technique mentioned in the message"
    )
    technique_context = context["related_entities"][technique_id]
    assert technique_context["connected_entities"], (
        "IntelligenceContextBuilder returned no related entities for the fresh technique"
    )
    assert any(
        entity["id"] == event_node_id for entity in technique_context["connected_entities"]
    ), "intelligence_context is not traceable to the freshly-ingested event, only to the technique"

    # --- Assertion 4: DecisionEngine (real routing evidence) ---
    result = DecisionEngine().evaluate(message, [], intelligence_context=context)
    assert result.domain_evidence, "DecisionEngine produced no domain evidence from real ingested data"
    assert result.domain_evidence["TOOL_USE"] > 0, (
        "an action-oriented message with real SKG evidence should influence TOOL_USE"
    )
    assert (
        max(result.domain_evidence.values()) <= DecisionEngine.DOMAIN_EVIDENCE_CAP + 1e-9
    ), "domain evidence exceeded its configured cap"
    # We are proving influence, not hard-routing -- selected_state is deliberately not asserted.


def test_real_wazuh_ingest_reaches_decision_engine_domain_evidence(tmp_path: Path) -> None:
    """real Wazuh alert -> persistent SKG/evidence -> GraphIntelligenceApi ->
    IntelligenceContextBuilder -> DecisionEngine -> non-zero domain evidence."""
    repository_root = _temp_repository(tmp_path)
    alert_id = "wazuh-integration-001"
    technique_id = "T1499"  # Endpoint Denial of Service -- unused elsewhere in this fixture.

    response = WazuhIngestApi(repository_root).ingest(_wazuh_alert(alert_id, technique_id))
    assert response["status"] == "accepted"

    _assert_pipeline_reaches_decision_engine(
        repository_root,
        event_node_id=f"event:{alert_id}",
        evidence_id=f"evidence:real-data-event-{alert_id}",
        technique_id=technique_id,
    )


def test_real_guardduty_ingest_reaches_decision_engine_domain_evidence(tmp_path: Path) -> None:
    """Same proof, GuardDuty source -- confirms the chain isn't Wazuh-specific."""
    repository_root = _temp_repository(tmp_path)
    finding_id = "guardduty-integration-001"
    technique_id = "T1071"

    response = GuardDutyIngestApi(repository_root).ingest(_guardduty_finding(finding_id))
    assert response["status"] == "accepted"

    _assert_pipeline_reaches_decision_engine(
        repository_root,
        event_node_id=f"event:{finding_id}",
        evidence_id=f"evidence:real-data-event-{finding_id}",
        technique_id=technique_id,
    )
