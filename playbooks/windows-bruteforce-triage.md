# Windows Brute Force Triage Playbook

## Trigger

Wazuh alert `SOC-WIN-AUTH-BRUTEFORCE-001` or repeated Windows Security Event ID `4625`.

## Initial Triage

1. Identify source IP, destination host, target account, and first/last event timestamps.
2. Count failed attempts within the detection window.
3. Check whether a successful logon followed the failures.
4. Review Sysmon process and network context on the target endpoint.
5. Check Suricata for SMB, RDP, or scanning activity from the same source.

## Escalation Criteria

Escalate to Tier 2 if:

- a successful logon follows the failure burst
- the source is not a known scanner or lab host
- multiple accounts are targeted
- privileged accounts are targeted
- endpoint telemetry shows suspicious post-authentication activity

## Containment

1. Disable or reset the targeted account if activity is unauthorized.
2. Block source IP at the lab firewall if needed.
3. Preserve logs and command transcripts.

## Closure

Document timeline, affected assets, user accounts, outcome, and tuning recommendations.
