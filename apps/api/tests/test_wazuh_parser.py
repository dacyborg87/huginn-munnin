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

from core.ingest.wazuh_parser import EventRecord, parse_wazuh_alert  # noqa: E402


def test_parse_wazuh_alert_extracts_core_fields() -> None:
    raw_alert = {
        "id": "1700000000.12345",
        "timestamp": "2026-06-08T14:22:31.000Z",
        "agent": {
            "id": "004",
            "name": "windows-endpoint-01",
        },
        "rule": {
            "id": "60122",
            "level": 10,
            "description": "Multiple Windows logon failures",
            "mitre": {
                "id": ["T1110", "T1078"],
                "tactic": ["Credential Access", "Defense Evasion"],
                "technique": ["Brute Force", "Valid Accounts"],
            },
        },
    }

    event = parse_wazuh_alert(raw_alert)

    assert event == EventRecord(
        id="1700000000.12345",
        timestamp="2026-06-08T14:22:31.000Z",
        source="wazuh",
        rule_id="60122",
        description="Multiple Windows logon failures",
        host="windows-endpoint-01",
        mitre_techniques=["T1110", "T1078"],
        severity="high",
    )


def test_parse_wazuh_alert_handles_single_mitre_id() -> None:
    raw_alert = {
        "id": "1700000001.999",
        "timestamp": "2026-06-08T15:10:05.000Z",
        "agent": {"name": "linux-web-01"},
        "rule": {
            "id": 5710,
            "level": "12",
            "description": "sshd brute force trying to get access",
            "mitre": {"id": "T1110"},
        },
    }

    event = parse_wazuh_alert(raw_alert)

    assert event.id == "1700000001.999"
    assert event.rule_id == "5710"
    assert event.host == "linux-web-01"
    assert event.mitre_techniques == ["T1110"]
    assert event.severity == "critical"


def test_parse_wazuh_alert_handles_missing_fields() -> None:
    event = parse_wazuh_alert({})

    assert event.id is None
    assert event.timestamp is None
    assert event.source == "wazuh"
    assert event.rule_id is None
    assert event.description is None
    assert event.host is None
    assert event.mitre_techniques == []
    assert event.severity is None


def test_parse_wazuh_alert_handles_partial_nested_data() -> None:
    raw_alert = {
        "id": "1700000002.111",
        "rule": {
            "level": 3,
            "mitre": {"id": [None, "T1046"]},
        },
    }

    event = parse_wazuh_alert(raw_alert)

    assert event.id == "1700000002.111"
    assert event.timestamp is None
    assert event.rule_id is None
    assert event.description is None
    assert event.host is None
    assert event.mitre_techniques == ["T1046"]
    assert event.severity == "low"


def test_parse_wazuh_alert_preserves_unknown_severity_text() -> None:
    raw_alert = {
        "rule": {
            "level": "informational",
        },
    }

    event = parse_wazuh_alert(raw_alert)

    assert event.severity == "informational"

