# Sysmon Detection Notes

Sysmon provides endpoint process, network, registry, and file telemetry for Windows labs.

Recommended event IDs for SOC labs:

| Event ID | Use |
| --- | --- |
| 1 | Process creation |
| 3 | Network connection |
| 7 | Image loaded |
| 10 | Process access |
| 11 | File create |
| 22 | DNS query |

Map Sysmon events to Wazuh alerts where possible and preserve raw event examples under `evidence/` after sanitization.
