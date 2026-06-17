"""Parse AWS GuardDuty findings into normalized EventRecord objects."""

from __future__ import annotations

import logging
from typing import Any

from core.ingest.wazuh_parser import EventRecord


LOGGER = logging.getLogger(__name__)

GUARDDUTY_MITRE_MAP: dict[str, list[str]] = {
    "Trojan:EC2/BlackholeTraffic": ["T1071"],
    "UnauthorizedAccess:IAMUser/ConsoleLoginSuccess.B": ["T1078"],
    "Recon:EC2/PortProbeUnprotectedPort": ["T1046"],
    "PrivilegeEscalation:IAMUser/AdministrativePermissions": ["T1078.004"],
    "Stealth:S3/ServerAccessLoggingDisabled": ["T1562.008"],
    "Impact:EC2/AbusedDomainRequest.Reputation": ["T1071.001"],
    "Exfiltration:S3/ObjectRead.Unusual": ["T1530"],
    "DefenseEvasion:IAMUser/AnomalousBehavior": ["T1078"],
    "CryptoCurrency:EC2/BitcoinTool.B": ["T1496"],
    "Backdoor:EC2/C&CActivity.B": ["T1071.001"],
}


class AwsGuardDutyParser:
    """Normalize AWS GuardDuty finding dictionaries into EventRecord objects."""

    def parse_finding(self, finding: dict[str, Any]) -> EventRecord | None:
        """Parse one GuardDuty finding, returning None for malformed findings."""

        try:
            if not isinstance(finding, dict):
                self._warn_skip("finding is not a dictionary")
                return None

            finding_id = self._optional_string(finding.get("id") or finding.get("Id"))
            timestamp = self._optional_string(finding.get("updatedAt") or finding.get("createdAt"))
            rule_id = self._optional_string(finding.get("type") or finding.get("Type"))

            if finding_id is None and timestamp is None and rule_id is None:
                self._warn_skip("missing id, timestamp, and rule_id")
                return None
            if finding_id is None:
                self._warn_skip("missing finding id")
                return None
            if timestamp is None:
                self._warn_skip("missing timestamp")
                return None
            if rule_id is None:
                self._warn_skip("missing finding type")
                return None

            description = self._optional_string(
                finding.get("title") or finding.get("description")
            ) or rule_id

            return EventRecord(
                id=finding_id,
                timestamp=timestamp,
                source="aws_guardduty",
                rule_id=rule_id,
                description=description,
                host=self._host(finding),
                mitre_techniques=list(GUARDDUTY_MITRE_MAP.get(rule_id, [])),
                severity=self._severity(finding.get("severity")),
            )
        except Exception as error:  # noqa: BLE001 - parser must never raise.
            self._warn_skip(f"unexpected parser error: {error}")
            return None

    def parse_findings(self, findings: list[dict[str, Any]]) -> list[EventRecord]:
        """Parse a list of GuardDuty findings, silently omitting invalid entries."""

        records = []
        skipped = 0
        for finding in findings:
            record = self.parse_finding(finding)
            if record is None:
                skipped += 1
                continue
            records.append(record)

        if skipped:
            LOGGER.warning("Skipped %s malformed GuardDuty finding(s).", skipped)
        return records

    @staticmethod
    def _host(finding: dict[str, Any]) -> str:
        resource = finding.get("resource")
        if not isinstance(resource, dict):
            return "aws_resource"

        instance_details = resource.get("instanceDetails")
        if isinstance(instance_details, dict):
            instance_id = instance_details.get("instanceId")
            if instance_id:
                return str(instance_id)

        resource_type = resource.get("resourceType")
        if resource_type:
            return str(resource_type)

        return "aws_resource"

    @staticmethod
    def _severity(value: Any) -> str:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return "unknown"

        if 0.1 <= numeric <= 3.9:
            return "low"
        if 4.0 <= numeric <= 6.9:
            return "medium"
        if 7.0 <= numeric <= 8.9:
            return "high"
        return "unknown"

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _warn_skip(reason: str) -> None:
        LOGGER.warning("Skipping GuardDuty finding: %s", reason)
