# Network Containment Playbook

## Trigger

Use this playbook when IDS or SIEM detections identify suspicious probing, scanning, or service discovery activity.

Mapped detections:

- `SOC-NET-SMB-PROBE-001`
- MITRE ATT&CK `T1046`

## Triage

1. Confirm source IP, destination IP, destination port, protocol, and detection timestamp.
2. Determine whether the source is a known scanner, lab attack host, or unexpected endpoint.
3. Review Wazuh and Suricata events for adjacent activity from the same source.
4. Check whether probing is followed by authentication attempts or exploitation indicators.

## Response

1. Block or isolate the source host when activity is unauthorized.
2. Capture relevant packet metadata and IDS alerts.
3. Preserve firewall, Suricata, and endpoint logs for correlation.
4. Escalate if scanning spans multiple hosts, privileged services, or production-like assets.

## Reporting

Document scope, services targeted, source classification, containment action, and tuning recommendations.
