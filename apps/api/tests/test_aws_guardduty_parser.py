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

from core.ingest.aws_guardduty_parser import (  # noqa: E402
    GUARDDUTY_MITRE_MAP,
    AwsGuardDutyParser,
)
from core.ingest.wazuh_parser import EventRecord  # noqa: E402


EC2_FINDING = {
    "id": "test-ec2-001",
    "type": "Trojan:EC2/BlackholeTraffic",
    "title": "EC2 instance communicating with known black hole IP",
    "severity": 8.0,
    "createdAt": "2026-06-17T00:00:00Z",
    "updatedAt": "2026-06-17T00:01:00Z",
    "resource": {
        "resourceType": "Instance",
        "instanceDetails": {
            "instanceId": "i-0abc123synthetic",
        },
    },
}

IAM_FINDING = {
    "id": "test-iam-001",
    "type": "UnauthorizedAccess:IAMUser/ConsoleLoginSuccess.B",
    "title": "IAM user logged in from unusual location",
    "severity": 5.0,
    "createdAt": "2026-06-17T00:00:00Z",
    "updatedAt": "2026-06-17T00:01:00Z",
    "resource": {
        "resourceType": "AccessKey",
        "accessKeyDetails": {
            "userName": "synthetic-user",
        },
    },
}

S3_FINDING = {
    "id": "test-s3-001",
    "type": "Stealth:S3/ServerAccessLoggingDisabled",
    "title": "S3 server access logging was disabled",
    "severity": 3.0,
    "createdAt": "2026-06-17T00:00:00Z",
    "updatedAt": "2026-06-17T00:01:00Z",
    "resource": {
        "resourceType": "S3Bucket",
    },
}


def parser() -> AwsGuardDutyParser:
    return AwsGuardDutyParser()


def test_ec2_finding_parses_to_event_record_without_raising() -> None:
    event = parser().parse_finding(EC2_FINDING)

    assert isinstance(event, EventRecord)


def test_ec2_finding_source_field_equals_aws_guardduty() -> None:
    event = parser().parse_finding(EC2_FINDING)

    assert event is not None
    assert event.source == "aws_guardduty"


def test_ec2_finding_host_equals_instance_id() -> None:
    event = parser().parse_finding(EC2_FINDING)

    assert event is not None
    assert event.host == "i-0abc123synthetic"


def test_ec2_finding_rule_id_equals_finding_type() -> None:
    event = parser().parse_finding(EC2_FINDING)

    assert event is not None
    assert event.rule_id == "Trojan:EC2/BlackholeTraffic"


def test_ec2_finding_mitre_techniques_are_mapped() -> None:
    event = parser().parse_finding(EC2_FINDING)

    assert event is not None
    assert event.mitre_techniques == ["T1071"]


def test_ec2_finding_severity_8_normalizes_to_high() -> None:
    event = parser().parse_finding(EC2_FINDING)

    assert event is not None
    assert event.severity == "high"


def test_iam_finding_host_falls_back_to_resource_type() -> None:
    event = parser().parse_finding(IAM_FINDING)

    assert event is not None
    assert event.host == "AccessKey"


def test_s3_finding_host_falls_back_to_resource_type() -> None:
    event = parser().parse_finding(S3_FINDING)

    assert event is not None
    assert event.host == "S3Bucket"


def test_finding_without_resource_host_falls_back_to_aws_resource() -> None:
    finding = {**EC2_FINDING}
    finding.pop("resource")

    event = parser().parse_finding(finding)

    assert event is not None
    assert event.host == "aws_resource"


def test_severity_5_normalizes_to_medium() -> None:
    event = parser().parse_finding(IAM_FINDING)

    assert event is not None
    assert event.severity == "medium"


def test_severity_2_normalizes_to_low() -> None:
    finding = {**S3_FINDING, "severity": 2.0}

    event = parser().parse_finding(finding)

    assert event is not None
    assert event.severity == "low"


def test_missing_severity_normalizes_to_unknown() -> None:
    finding = {**EC2_FINDING}
    finding.pop("severity")

    event = parser().parse_finding(finding)

    assert event is not None
    assert event.severity == "unknown"


def test_unmapped_finding_type_returns_empty_mitre_techniques() -> None:
    finding = {**EC2_FINDING, "type": "Unmapped:Finding/Type"}

    event = parser().parse_finding(finding)

    assert event is not None
    assert event.mitre_techniques == []


def test_finding_missing_id_returns_none() -> None:
    finding = {**EC2_FINDING}
    finding.pop("id")

    assert parser().parse_finding(finding) is None


def test_finding_missing_timestamp_returns_none() -> None:
    finding = {**EC2_FINDING}
    finding.pop("updatedAt")
    finding.pop("createdAt")

    assert parser().parse_finding(finding) is None


def test_non_dict_input_returns_none() -> None:
    assert parser().parse_finding("not-a-finding") is None  # type: ignore[arg-type]


def test_parse_findings_with_mixed_valid_and_invalid_returns_only_valid_records() -> None:
    finding_without_id = {**EC2_FINDING}
    finding_without_id.pop("id")

    records = parser().parse_findings([EC2_FINDING, finding_without_id, "bad"])  # type: ignore[list-item]

    assert len(records) == 1
    assert records[0].id == "test-ec2-001"


def test_guardduty_mitre_map_is_importable_module_level_constant() -> None:
    assert GUARDDUTY_MITRE_MAP["Trojan:EC2/BlackholeTraffic"] == ["T1071"]
