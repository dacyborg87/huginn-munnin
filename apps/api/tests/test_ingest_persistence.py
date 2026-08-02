import json
import multiprocessing
import shutil
import sys
import types
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPOSITORY_ROOT / "apps" / "api" / "src"
if str(API_SRC) in sys.path:
    sys.path.remove(str(API_SRC))
sys.path.insert(0, str(API_SRC))
core_package = types.ModuleType("core")
core_package.__path__ = [str(REPOSITORY_ROOT / "core")]
sys.modules["core"] = core_package

from core.evidence_schema import (  # noqa: E402
    ConfidenceBreakdown,
    ConfidenceFactor,
    ConfidenceLevel,
    EvidenceRecord,
    EvidenceSourceType,
    RelatedEvidenceEntities,
    save_evidence_index,
)
from core.knowledge_graph import KnowledgeGraph  # noqa: E402
from huginn_muninn_api.core.evidence_api import EvidenceApi  # noqa: E402
from huginn_muninn_api.core.graph_intelligence_api import GraphIntelligenceApi  # noqa: E402
from huginn_muninn_api.core.guardduty_ingest_api import GuardDutyIngestApi  # noqa: E402
from huginn_muninn_api.core.wazuh_ingest_api import WazuhIngestApi  # noqa: E402


def _wazuh_process_worker(
    repository_root: str,
    alert_id: str,
    start_event: multiprocessing.Event,
    queue: multiprocessing.Queue,
) -> None:
    start_event.wait(5)
    try:
        response = WazuhIngestApi(Path(repository_root)).ingest(_wazuh_alert(alert_id))
    except Exception as error:  # noqa: BLE001 - test worker must report failures.
        queue.put(("error", alert_id, repr(error)))
        return
    queue.put(("ok", alert_id, response))


def _guardduty_process_worker(
    repository_root: str,
    finding_id: str,
    start_event: multiprocessing.Event,
    queue: multiprocessing.Queue,
) -> None:
    start_event.wait(5)
    try:
        response = GuardDutyIngestApi(Path(repository_root)).ingest(
            _guardduty_finding(finding_id)
        )
    except Exception as error:  # noqa: BLE001 - test worker must report failures.
        queue.put(("error", finding_id, repr(error)))
        return
    queue.put(("ok", finding_id, response))


def _temp_repository(tmp_path: Path) -> Path:
    shutil.copytree(REPOSITORY_ROOT / "core", tmp_path / "core")
    (tmp_path / "reports").mkdir()
    (tmp_path / "core" / "patterns").mkdir(exist_ok=True)
    return tmp_path


def _seed_graph(repository_root: Path) -> None:
    graph = KnowledgeGraph()
    graph.add_node(
        "event:existing-event",
        "Event",
        "Existing event",
        {"source_system": "seed", "timestamp": "2026-06-01T00:00:00Z"},
    )
    graph.add_node(
        "mitre:T0001",
        "MITRE Technique",
        "T0001",
        {"technique_id": "T0001"},
    )
    graph.add_relationship("event:existing-event", "relates_to", "mitre:T0001")
    graph.save(repository_root / "reports" / "knowledge-graph.json")


def _seed_evidence(repository_root: Path) -> None:
    save_evidence_index(
        repository_root / "reports" / "evidence-index.json",
        [
            EvidenceRecord(
                evidence_id="evidence:existing-record",
                title="Existing evidence",
                summary="Existing evidence tied to the seeded event.",
                source_type=EvidenceSourceType.DETECTION_ALERT,
                source_path="reports/existing.json",
                source_reference="event:existing-event",
                timestamp="2026-06-01T00:00:00Z",
                related_entities=RelatedEvidenceEntities(events=["event:existing-event"]),
                confidence=ConfidenceBreakdown(
                    score=0.8,
                    level=ConfidenceLevel.HIGH,
                    calculation={
                        "source_reliability": ConfidenceFactor(
                            weight=1.0,
                            value=0.8,
                            weighted_score=0.8,
                        )
                    },
                    explanation="Existing seeded evidence is high confidence.",
                ),
            )
        ],
    )


def _wazuh_alert(alert_id: str = "wazuh-persist-001") -> dict[str, Any]:
    return {
        "id": alert_id,
        "timestamp": "2026-06-17T12:00:00.000Z",
        "agent": {"name": "windows-endpoint-01"},
        "rule": {
            "id": "60122",
            "level": 10,
            "description": "Multiple Windows logon failures",
            "mitre": {"id": ["T1110"]},
        },
    }


def _guardduty_finding(finding_id: str = "guardduty-persist-001") -> dict[str, Any]:
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


def _read_graph(repository_root: Path) -> dict[str, Any]:
    return json.loads(
        (repository_root / "reports" / "knowledge-graph.json").read_text(
            encoding="utf-8",
        )
    )


def _read_evidence(repository_root: Path) -> dict[str, Any]:
    return json.loads(
        (repository_root / "reports" / "evidence-index.json").read_text(
            encoding="utf-8",
        )
    )


def _read_summary(repository_root: Path) -> dict[str, Any]:
    return json.loads(
        (repository_root / "core" / "patterns" / "knowledge-graph-summary.json").read_text(
            encoding="utf-8",
        )
    )


def _queue_results(
    queue: multiprocessing.Queue,
    expected_count: int,
) -> list[tuple[str, str, Any]]:
    results = [queue.get(timeout=1) for _ in range(expected_count)]
    errors = [result for result in results if result[0] != "ok"]
    assert errors == []
    return results


def test_wazuh_ingestion_persists_graph_summary_and_evidence(tmp_path: Path) -> None:
    repository_root = _temp_repository(tmp_path)
    _seed_graph(repository_root)
    _seed_evidence(repository_root)

    response = WazuhIngestApi(repository_root).ingest(_wazuh_alert())

    graph = json.loads(
        (repository_root / "reports" / "knowledge-graph.json").read_text(
            encoding="utf-8",
        )
    )
    node_ids = {node["id"] for node in graph["nodes"]}
    relationship_ids = {relationship["id"] for relationship in graph["relationships"]}
    evidence = json.loads(
        (repository_root / "reports" / "evidence-index.json").read_text(
            encoding="utf-8",
        )
    )
    evidence_ids = {record["evidence_id"] for record in evidence["evidence"]}
    summary = json.loads(
        (repository_root / "core" / "patterns" / "knowledge-graph-summary.json").read_text(
            encoding="utf-8",
        )
    )

    assert response["status"] == "accepted"
    assert "event:existing-event" in node_ids
    assert "event:wazuh-persist-001" in node_ids
    assert "mitre:T1110" in node_ids
    assert "event:wazuh-persist-001:relates_to:mitre:T1110" in relationship_ids
    assert "evidence:existing-record" in evidence_ids
    assert "evidence:real-data-event-wazuh-persist-001" in evidence_ids
    assert summary["total_nodes"] == len(graph["nodes"])
    assert summary["total_relationships"] == len(graph["relationships"])
    assert (repository_root / "reports" / "real-data-pipeline-output.json").exists()


def test_guardduty_ingestion_persists_graph_summary_and_evidence(tmp_path: Path) -> None:
    repository_root = _temp_repository(tmp_path)
    _seed_graph(repository_root)
    _seed_evidence(repository_root)

    response = GuardDutyIngestApi(repository_root).ingest(_guardduty_finding())

    graph = json.loads(
        (repository_root / "reports" / "knowledge-graph.json").read_text(
            encoding="utf-8",
        )
    )
    node_ids = {node["id"] for node in graph["nodes"]}
    relationship_ids = {relationship["id"] for relationship in graph["relationships"]}
    evidence = json.loads(
        (repository_root / "reports" / "evidence-index.json").read_text(
            encoding="utf-8",
        )
    )
    evidence_ids = {record["evidence_id"] for record in evidence["evidence"]}
    summary = json.loads(
        (repository_root / "core" / "patterns" / "knowledge-graph-summary.json").read_text(
            encoding="utf-8",
        )
    )

    assert response["status"] == "accepted"
    assert response["source"] == "aws_guardduty"
    assert "event:existing-event" in node_ids
    assert "event:guardduty-persist-001" in node_ids
    assert "mitre:T1071" in node_ids
    assert "event:guardduty-persist-001:relates_to:mitre:T1071" in relationship_ids
    assert "evidence:existing-record" in evidence_ids
    assert "evidence:real-data-event-guardduty-persist-001" in evidence_ids
    assert summary["total_nodes"] == len(graph["nodes"])
    assert summary["total_relationships"] == len(graph["relationships"])


def test_duplicate_wazuh_ingestion_does_not_duplicate_persisted_records(
    tmp_path: Path,
) -> None:
    repository_root = _temp_repository(tmp_path)
    api = WazuhIngestApi(repository_root)

    first = api.ingest(_wazuh_alert())
    second = api.ingest(_wazuh_alert())

    graph = json.loads(
        (repository_root / "reports" / "knowledge-graph.json").read_text(
            encoding="utf-8",
        )
    )
    evidence = json.loads(
        (repository_root / "reports" / "evidence-index.json").read_text(
            encoding="utf-8",
        )
    )
    relationship_ids = [
        relationship["id"]
        for relationship in graph["relationships"]
        if relationship["id"] == "event:wazuh-persist-001:relates_to:mitre:T1110"
    ]
    evidence_ids = [
        record["evidence_id"]
        for record in evidence["evidence"]
        if record["evidence_id"] == "evidence:real-data-event-wazuh-persist-001"
    ]

    assert first["events_added"] == 1
    assert second["events_added"] == 0
    assert relationship_ids == ["event:wazuh-persist-001:relates_to:mitre:T1110"]
    assert evidence_ids == ["evidence:real-data-event-wazuh-persist-001"]


def test_new_wazuh_event_is_visible_through_graph_and_evidence_queries(
    tmp_path: Path,
) -> None:
    repository_root = _temp_repository(tmp_path)

    WazuhIngestApi(repository_root).ingest(_wazuh_alert())

    graph_response = GraphIntelligenceApi(repository_root).related("wazuh-persist-001")
    evidence_response = EvidenceApi(repository_root).finding("event:wazuh-persist-001")

    assert graph_response["normalized_entity"] == "event:wazuh-persist-001"
    assert any(
        entity["id"] == "mitre:T1110"
        for entity in graph_response["connected_entities"]
    )
    assert evidence_response["match_count"] == 1
    assert (
        evidence_response["evidence_records"][0]["source_reference"]
        == "event:wazuh-persist-001"
    )


def test_simultaneous_unique_wazuh_ingests_preserve_every_event(
    tmp_path: Path,
) -> None:
    repository_root = _temp_repository(tmp_path)
    start_event = multiprocessing.Event()
    queue: multiprocessing.Queue = multiprocessing.Queue()
    alert_ids = [f"wazuh-concurrent-{index}" for index in range(6)]
    processes = [
        multiprocessing.Process(
            target=_wazuh_process_worker,
            args=(str(repository_root), alert_id, start_event, queue),
        )
        for alert_id in alert_ids
    ]

    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=10)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            raise AssertionError("Wazuh ingestion process timed out")
        assert process.exitcode == 0
    _queue_results(queue, len(processes))

    graph = _read_graph(repository_root)
    summary = _read_summary(repository_root)
    node_ids = {node["id"] for node in graph["nodes"]}
    relationship_ids = {relationship["id"] for relationship in graph["relationships"]}

    for alert_id in alert_ids:
        assert f"event:{alert_id}" in node_ids
        assert f"event:{alert_id}:relates_to:mitre:T1110" in relationship_ids
    assert summary["total_nodes"] == len(graph["nodes"])
    assert summary["total_relationships"] == len(graph["relationships"])


def test_simultaneous_wazuh_and_guardduty_ingests_preserve_both_sources(
    tmp_path: Path,
) -> None:
    repository_root = _temp_repository(tmp_path)
    start_event = multiprocessing.Event()
    queue: multiprocessing.Queue = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(
            target=_wazuh_process_worker,
            args=(str(repository_root), "wazuh-mixed-001", start_event, queue),
        ),
        multiprocessing.Process(
            target=_guardduty_process_worker,
            args=(str(repository_root), "guardduty-mixed-001", start_event, queue),
        ),
    ]

    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=10)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            raise AssertionError("mixed ingestion process timed out")
        assert process.exitcode == 0
    _queue_results(queue, len(processes))

    graph = _read_graph(repository_root)
    evidence = _read_evidence(repository_root)
    summary = _read_summary(repository_root)
    node_ids = {node["id"] for node in graph["nodes"]}
    relationship_ids = {relationship["id"] for relationship in graph["relationships"]}
    evidence_ids = {record["evidence_id"] for record in evidence["evidence"]}

    assert "event:wazuh-mixed-001" in node_ids
    assert "event:guardduty-mixed-001" in node_ids
    assert "event:wazuh-mixed-001:relates_to:mitre:T1110" in relationship_ids
    assert "event:guardduty-mixed-001:relates_to:mitre:T1071" in relationship_ids
    assert "evidence:real-data-event-wazuh-mixed-001" in evidence_ids
    assert "evidence:real-data-event-guardduty-mixed-001" in evidence_ids
    assert summary["total_nodes"] == len(graph["nodes"])
    assert summary["total_relationships"] == len(graph["relationships"])


def test_simultaneous_duplicate_wazuh_ingestion_deduplicates_evidence(
    tmp_path: Path,
) -> None:
    repository_root = _temp_repository(tmp_path)
    start_event = multiprocessing.Event()
    queue: multiprocessing.Queue = multiprocessing.Queue()
    processes = [
        multiprocessing.Process(
            target=_wazuh_process_worker,
            args=(str(repository_root), "wazuh-duplicate-001", start_event, queue),
        )
        for _ in range(4)
    ]

    for process in processes:
        process.start()
    start_event.set()
    for process in processes:
        process.join(timeout=10)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            raise AssertionError("duplicate ingestion process timed out")
        assert process.exitcode == 0
    _queue_results(queue, len(processes))

    graph = _read_graph(repository_root)
    evidence = _read_evidence(repository_root)
    relationship_ids = [
        relationship["id"]
        for relationship in graph["relationships"]
        if relationship["id"] == "event:wazuh-duplicate-001:relates_to:mitre:T1110"
    ]
    evidence_ids = [
        record["evidence_id"]
        for record in evidence["evidence"]
        if record["evidence_id"] == "evidence:real-data-event-wazuh-duplicate-001"
    ]

    assert relationship_ids == ["event:wazuh-duplicate-001:relates_to:mitre:T1110"]
    assert evidence_ids == ["evidence:real-data-event-wazuh-duplicate-001"]


def test_persistence_failure_raises_and_does_not_write_success_pipeline_report(
    tmp_path: Path,
) -> None:
    repository_root = _temp_repository(tmp_path)
    api = WazuhIngestApi(repository_root)
    modules = api._repository_modules()
    original_atomic_write_json = modules["atomic_write_json"]

    def fail_summary_write(path: Path, payload: Any) -> None:
        if str(path).endswith("knowledge-graph-summary.json"):
            raise OSError("summary write failed")
        original_atomic_write_json(path, payload)

    modules = {**modules, "atomic_write_json": fail_summary_write}
    api._repository_modules = lambda: modules  # type: ignore[method-assign]

    try:
        api.ingest(_wazuh_alert("wazuh-failure-001"))
    except OSError as error:
        assert str(error) == "summary write failed"
    else:
        raise AssertionError("expected persistence failure to propagate")

    assert not (repository_root / "reports" / "real-data-pipeline-output.json").exists()
