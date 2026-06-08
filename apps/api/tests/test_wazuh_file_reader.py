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

from core.ingest.wazuh_file_reader import read_wazuh_alert_file  # noqa: E402
from core.ingest.wazuh_parser import EventRecord  # noqa: E402


def _wazuh_alert(alert_id: str = "1700000000.12345") -> dict:
    return {
        "id": alert_id,
        "timestamp": "2026-06-08T14:22:31.000Z",
        "agent": {"name": "windows-endpoint-01"},
        "rule": {
            "id": "60122",
            "level": 10,
            "description": "Multiple Windows logon failures",
            "mitre": {"id": ["T1110", "T1078"]},
        },
    }


def test_read_wazuh_alert_file_supports_single_alert(tmp_path: Path) -> None:
    input_path = tmp_path / "alerts.json"
    input_path.write_text(json.dumps(_wazuh_alert()), encoding="utf-8")

    result = read_wazuh_alert_file(input_path)

    assert result.summary["records_read"] == 1
    assert result.summary["records_parsed"] == 1
    assert result.summary["records_skipped"] == 0
    assert result.summary["source_path"] == str(input_path)
    assert result.events == [
        EventRecord(
            id="1700000000.12345",
            timestamp="2026-06-08T14:22:31.000Z",
            source="wazuh",
            rule_id="60122",
            description="Multiple Windows logon failures",
            host="windows-endpoint-01",
            mitre_techniques=["T1110", "T1078"],
            severity="high",
        )
    ]


def test_read_wazuh_alert_file_supports_list_of_alerts(tmp_path: Path) -> None:
    input_path = tmp_path / "alerts.json"
    input_path.write_text(
        json.dumps([
            _wazuh_alert("1700000000.12345"),
            _wazuh_alert("1700000001.999"),
        ]),
        encoding="utf-8",
    )

    result = read_wazuh_alert_file(input_path)

    assert result.summary["records_read"] == 2
    assert result.summary["records_parsed"] == 2
    assert result.summary["records_skipped"] == 0
    assert [event.id for event in result.events] == [
        "1700000000.12345",
        "1700000001.999",
    ]


def test_read_wazuh_alert_file_skips_malformed_records(tmp_path: Path) -> None:
    input_path = tmp_path / "alerts.json"
    input_path.write_text(
        json.dumps([
            _wazuh_alert("1700000000.12345"),
            "not an alert",
            42,
        ]),
        encoding="utf-8",
    )

    result = read_wazuh_alert_file(input_path)

    assert result.summary["records_read"] == 3
    assert result.summary["records_parsed"] == 1
    assert result.summary["records_skipped"] == 2
    assert len(result.events) == 1


def test_read_wazuh_alert_file_handles_invalid_json(tmp_path: Path) -> None:
    input_path = tmp_path / "alerts.json"
    input_path.write_text("{not valid json", encoding="utf-8")

    result = read_wazuh_alert_file(input_path)

    assert result.events == []
    assert result.summary["records_read"] == 0
    assert result.summary["records_parsed"] == 0
    assert result.summary["records_skipped"] == 1
    assert result.summary["source_path"] == str(input_path)
    assert "error" in result.summary


def test_read_wazuh_alert_file_handles_missing_file(tmp_path: Path) -> None:
    input_path = tmp_path / "missing-alerts.json"

    result = read_wazuh_alert_file(input_path)

    assert result.events == []
    assert result.summary["records_read"] == 0
    assert result.summary["records_parsed"] == 0
    assert result.summary["records_skipped"] == 1
    assert result.summary["source_path"] == str(input_path)
    assert "error" in result.summary
