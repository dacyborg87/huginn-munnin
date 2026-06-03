# Detection Engine

Detection content is organized by telemetry source and follows consistent naming.

## Naming Convention

```text
SOC-<SOURCE>-<BEHAVIOR>-<NUMBER>
```

Examples:

- `SOC-WIN-AUTH-BRUTEFORCE-001`
- `SOC-NET-SMB-PROBE-001`

## Required Rule Metadata

Every detection must include:

- rule name
- short objective
- data source
- MITRE ATT&CK tactic and technique ID
- severity or priority
- false-positive notes
- test procedure

## Directories

```text
detection-engine/
  wazuh/rules/
  suricata/rules/
  sysmon/
  auditd/
```

## Validation

Run XML validation for Wazuh rules:

```bash
python scripts/validate_wazuh_rules.py
```
