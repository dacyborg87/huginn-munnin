import json
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

from core.ingest.wazuh_pipeline import (  # noqa: E402
    generate_sample_wazuh_pipeline_output,
    run_wazuh_file_pipeline,
)


def _alert(alert_id: str, mitre_ids: list[str] | None = None) -> dict:
    rule = {
        "id": "60122",
        "level": 10,
        "description": "Multiple Windows logon failures",
    }
    if mitre_ids:
        rule["mitre"] = {"id": mitre_ids}
    return {
        "id": alert_id,
        "timestamp": "2026-06-08T14:22:31.000Z",
        "agent": {"name": "windows-endpoint-01"},
        "rule": rule,
    }


def test_run_wazuh_file_pipeline_orchestrates_reader_graph_and_evidence(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "alerts.json"
    input_path.write_text(
        json.dumps([
            _alert("1700000000.12345", ["T1110", "T1078"]),
            _alert("1700000002.111"),
            "malformed alert",
        ]),
        encoding="utf-8",
    )

    output = run_wazuh_file_pipeline(input_path, persist=False)

    assert output["summary"] == {
        "records_read": 3,
        "records_parsed": 2,
        "records_skipped": 1,
        "events_added": 2,
        "techniques_added": 2,
        "relationships_added": 2,
        "duplicates_skipped": 0,
        "evidence_records_created": 2,
        "evidence_gaps_created": 1,
    }
    assert len(output["evidence_records"]) == 2
    assert output["explanation"]


def test_run_wazuh_file_pipeline_persists_output(tmp_path: Path) -> None:
    input_path = tmp_path / "alerts.json"
    output_path = tmp_path / "real-data-pipeline-output.json"
    input_path.write_text(
        json.dumps(_alert("1700000000.12345", ["T1110"])),
        encoding="utf-8",
    )

    output = run_wazuh_file_pipeline(input_path, output_path=output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload == output
    assert payload["schema_version"] == "1.0"
    assert payload["summary"]["records_parsed"] == 1
    assert payload["summary"]["evidence_records_created"] == 1


def test_run_wazuh_file_pipeline_handles_invalid_json(tmp_path: Path) -> None:
    input_path = tmp_path / "alerts.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    output = run_wazuh_file_pipeline(input_path, persist=False)

    assert output["summary"]["records_read"] == 0
    assert output["summary"]["records_parsed"] == 0
    assert output["summary"]["records_skipped"] == 1
    assert output["summary"]["events_added"] == 0
    assert output["summary"]["evidence_records_created"] == 0
    assert output["summary"]["evidence_gaps_created"] == 0
    assert output["evidence_records"] == []
    assert "error" in output


def test_run_wazuh_file_pipeline_handles_empty_list(tmp_path: Path) -> None:
    input_path = tmp_path / "alerts.json"
    input_path.write_text("[]", encoding="utf-8")

    output = run_wazuh_file_pipeline(input_path, persist=False)

    assert output["summary"] == {
        "records_read": 0,
        "records_parsed": 0,
        "records_skipped": 0,
        "events_added": 0,
        "techniques_added": 0,
        "relationships_added": 0,
        "duplicates_skipped": 0,
        "evidence_records_created": 0,
        "evidence_gaps_created": 0,
    }
    assert output["evidence_records"] == []


def test_committed_sample_wazuh_pipeline_output_loads() -> None:
    output = generate_sample_wazuh_pipeline_output(
        REPOSITORY_ROOT / "reports" / "real-data-pipeline-output.json"
    )
    payload = json.loads(
        (REPOSITORY_ROOT / "reports" / "real-data-pipeline-output.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload == output
    assert payload["summary"]["records_read"] == 3
    assert payload["summary"]["records_parsed"] == 2
    assert payload["summary"]["records_skipped"] == 1
    assert payload["summary"]["evidence_records_created"] == 2
    assert payload["summary"]["evidence_gaps_created"] == 1
