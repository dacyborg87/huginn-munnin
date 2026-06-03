# Lab 001: Windows Authentication Brute Force

## Objective

Detect repeated failed Windows authentication attempts and produce a SOC-style incident report using Wazuh, Sysmon, Windows Security logs, and supporting network telemetry.

## Attack Scenario

An attacker on a Kali host attempts password guessing against a Windows endpoint. The expected telemetry includes repeated Windows Security Event ID `4625`, optional Sysmon network process context, and possible Suricata network indicators for SMB or RDP connection attempts.

## MITRE ATT&CK Mapping

| Tactic | Technique | ID | Detection Source |
| --- | --- | --- | --- |
| Credential Access | Brute Force | T1110 | Windows Security, Wazuh |
| Defense Evasion / Initial Access | Valid Accounts | T1078 | Windows Security, Wazuh |
| Discovery | Network Service Discovery | T1046 | Suricata |

## Setup Steps

1. Confirm Wazuh agent is installed on the Windows endpoint.
2. Enable Windows Security audit policy for logon failures.
3. Install Sysmon with a known-good configuration.
4. Confirm Suricata is monitoring the lab network segment.
5. Add Wazuh rule `SOC-WIN-AUTH-BRUTEFORCE-001`.
6. Add Suricata rule `SOC-NET-SMB-PROBE-001`.
7. Restart Wazuh manager and Suricata after rule deployment.

## Attack Execution Steps

Authorized lab use only.

1. From Kali, identify the Windows target IP.
2. Attempt repeated authentication failures against SMB or RDP using a controlled test account.
3. Stop after the detection threshold is reached.
4. Preserve timestamps, source IP, target IP, username, and command transcript.

## Detection Rules

### Wazuh

- Rule file: `detection-engine/wazuh/rules/001-windows-auth-bruteforce.xml`
- Rule name: `SOC-WIN-AUTH-BRUTEFORCE-001`
- MITRE: `T1110`

### Suricata

- Rule file: `detection-engine/suricata/rules/001-smb-probe.rules`
- Rule name: `SOC-NET-SMB-PROBE-001`
- MITRE: `T1046`

## Evidence

Store sanitized evidence under:

```text
evidence/001-windows-auth-bruteforce/
```

Recommended artifacts:

- Wazuh alert JSON
- Windows Security event export
- Sysmon event export
- Suricata `eve.json` excerpts
- Attack command transcript
- Timeline notes

Do not commit credentials, real usernames, internal IP addresses from non-lab networks, or unsanitized packet captures.

## Incident Report

### Timeline

| Time | Event | Source |
| --- | --- | --- |
| TBD | Repeated failed logons observed | Windows Security / Wazuh |
| TBD | Network connection attempts observed | Suricata |
| TBD | Analyst triage started | Playbook |

### Impact

Potential credential access attempt against a Windows endpoint. Impact is limited to lab systems if test account controls were followed.

### Response

1. Identify source IP and target account.
2. Confirm whether failures are expected lab activity.
3. Check for successful logon after failure burst.
4. Review endpoint process and network context.
5. Disable or rotate the test account if the activity was not authorized.

### Lessons Learned

- Tune thresholds to reduce noisy failed-logon bursts.
- Add correlation for failure-to-success patterns.
- Preserve source host context from Sysmon and network logs.
