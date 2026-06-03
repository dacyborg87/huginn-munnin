# Account Lockout Playbook

## Trigger

Use this playbook when a brute-force or password spraying detection indicates repeated authentication failures against one or more accounts.

Mapped detections:

- `SOC-WIN-AUTH-BRUTEFORCE-001`
- MITRE ATT&CK `T1110`

## Triage

1. Confirm source IP, target host, target account, and first/last observed timestamps.
2. Identify whether a successful logon occurred after the failure burst.
3. Check whether the source is expected lab infrastructure, a scanner, or an unauthorized host.
4. Review endpoint telemetry for new processes, remote sessions, or privilege changes.

## Response

1. Lock or reset the targeted account when unauthorized activity is confirmed.
2. Block the source IP if activity is not expected in the lab scenario.
3. Preserve Wazuh, Windows Security, Sysmon, and firewall evidence.
4. Escalate to Tier 2 if privileged accounts, multiple hosts, or post-authentication activity are observed.

## Reporting

Document the authentication timeline, affected assets, account impact, containment action, and false-positive assessment.
