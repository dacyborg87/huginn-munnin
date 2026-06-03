# Evidence

Store sanitized lab evidence here.

Recommended structure:

```text
evidence/
  001-windows-auth-bruteforce/
    wazuh-alert.json
    windows-security-events.evtx.txt
    sysmon-events.json
    suricata-eve-excerpt.json
    attack-transcript.txt
```

Do not commit:

- real credentials
- real tokens
- private keys
- unsanitized packet captures
- non-lab IP addresses
- personal data
- production logs
