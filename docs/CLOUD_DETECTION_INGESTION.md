# Cloud Detection Ingestion

## 1. Purpose

The GuardDuty parser normalizes AWS GuardDuty finding dictionaries into the
same `EventRecord` structure used by the existing Wazuh ingestion pipeline.

It fits into the Huginn/Muninn platform as a cloud telemetry adapter:

```text
AWS GuardDuty finding
-> AwsGuardDutyParser
-> EventRecord
-> Graph Ingest
-> Real Data Evidence
-> Knowledge Graph and dashboard-ready reports
```

Reusing `EventRecord` matters because downstream modules such as graph ingest
and real-data evidence already understand that shape. GuardDuty findings can
therefore enter the same intelligence path without changing Wazuh ingestion,
graph logic, or evidence schemas.

## 2. Field Mapping Table

| EventRecord field | GuardDuty source | Notes |
| --- | --- | --- |
| `id` | `id` or `Id` | Required. Missing value causes the finding to be skipped. |
| `timestamp` | `updatedAt` or `createdAt` | Required. `updatedAt` is preferred. |
| `source` | hardcoded | Always `aws_guardduty`. |
| `rule_id` | `type` or `Type` | Required. Represents the GuardDuty finding type. |
| `description` | `title` or `description` | Falls back to `rule_id`. |
| `host` | resource details | Uses the fallback order described below. |
| `mitre_techniques` | `GUARDDUTY_MITRE_MAP[rule_id]` | Empty list when no static mapping exists. |
| `severity` | `severity` | Numeric GuardDuty severity normalized to text. |

## 3. MITRE Lookup Table

| Finding type | Technique ID | Technique name |
| --- | --- | --- |
| `Trojan:EC2/BlackholeTraffic` | `T1071` | Application Layer Protocol |
| `UnauthorizedAccess:IAMUser/ConsoleLoginSuccess.B` | `T1078` | Valid Accounts |
| `Recon:EC2/PortProbeUnprotectedPort` | `T1046` | Network Service Discovery |
| `PrivilegeEscalation:IAMUser/AdministrativePermissions` | `T1078.004` | Cloud Accounts |
| `Stealth:S3/ServerAccessLoggingDisabled` | `T1562.008` | Disable Cloud Logs |
| `Impact:EC2/AbusedDomainRequest.Reputation` | `T1071.001` | Web Protocols |
| `Exfiltration:S3/ObjectRead.Unusual` | `T1530` | Data from Cloud Storage |
| `DefenseEvasion:IAMUser/AnomalousBehavior` | `T1078` | Valid Accounts |
| `CryptoCurrency:EC2/BitcoinTool.B` | `T1496` | Resource Hijacking |
| `Backdoor:EC2/C&CActivity.B` | `T1071.001` | Web Protocols |

## 4. Host Extraction Logic

The parser extracts the affected resource using a three-level fallback:

1. Use `resource.instanceDetails.instanceId` when an EC2 instance ID exists.
2. Otherwise use `resource.resourceType`, such as `AccessKey` or `S3Bucket`.
3. If no resource context is available, use `aws_resource`.

Every lookup uses `.get()` style access and missing nested fields do not raise
exceptions.

## 5. Severity Normalization

| Numeric range | Normalized value |
| --- | --- |
| `0.1` to `3.9` | `low` |
| `4.0` to `6.9` | `medium` |
| `7.0` to `8.9` | `high` |
| missing, `None`, non-numeric, or out of range | `unknown` |

## 6. Known Limitations

- No live GuardDuty API integration exists yet.
- The static MITRE map covers common findings only.
- Resource extraction is optimized for EC2, IAM, and S3 finding types.
- No deduplication is currently performed in graph ingest.
- The parser accepts dictionaries only and does not read files.
- No AWS SDK, `boto3`, or `botocore` dependency is used.

## 7. How To Extend The MITRE Map

The static lookup lives in `core/ingest/aws_guardduty_parser.py` as
`GUARDDUTY_MITRE_MAP`.

To add a new mapping, add the exact GuardDuty finding type as the key and a list
of MITRE ATT&CK technique IDs as the value.

Keep mappings conservative and document any new mapping with a test fixture so
future reviewers can verify why the technique is attached.

## 8. How To Add A New Cloud Parser

1. Create a new module under `core/ingest/`.
2. Reuse the frozen `EventRecord` dataclass without modifying it.
3. Convert the cloud provider finding into `id`, `timestamp`, `source`,
   `rule_id`, `description`, `host`, `mitre_techniques`, and `severity`.
4. Handle malformed records by returning `None` instead of raising.
5. Add a parser method for one finding and another method for a list of findings.
6. Add synthetic direct unit tests under `apps/api/tests/`.
7. Document field mapping, severity handling, MITRE lookup, and limitations.
