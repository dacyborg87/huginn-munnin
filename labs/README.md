# Labs

Labs are structured SOC detection engineering scenarios. Each lab should be evidence-driven and mapped to MITRE ATT&CK.

## Required Lab Structure

Each lab README must include:

- Objective
- Attack scenario
- MITRE ATT&CK mapping
- Setup steps
- Attack execution steps
- Detection rules: Wazuh and Suricata
- Evidence section
- Incident report: timeline, impact, response, lessons learned

Use [templates/lab-readme-template.md](../templates/lab-readme-template.md) for new labs.

## Current Labs

| Lab | Focus | Techniques |
| --- | --- | --- |
| `001-windows-auth-bruteforce` | Windows authentication brute force detection | T1110, T1078 |
