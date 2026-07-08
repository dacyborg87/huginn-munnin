# Evidence

Store sanitized artifact exports from completed lab scenarios here.

Each lab gets its own subdirectory named to match the lab number:

```text
evidence/
  001-windows-auth-bruteforce/
    wazuh-alert.json
    windows-security-events.evtx.txt
    sysmon-events.json
    suricata-eve-excerpt.json
    timeline-notes.md
    attack-transcript.txt
```

See [labs/001-windows-auth-bruteforce/README.md](../labs/001-windows-auth-bruteforce/README.md) for the full lab guide and setup steps.

## What to include

- Sanitized Wazuh alert JSON exports
- Windows Security event excerpts
- Sysmon event exports
- Suricata `eve.json` excerpts
- Attack command transcripts (lab environment only)
- Timeline notes and analyst observations

## What NOT to commit

- Real credentials, passwords, or API keys
- Unsanitized packet captures containing private network information
- Real usernames or internal IP addresses from non-lab environments
- Private keys or tokens of any kind
- Production logs or data from non-lab systems
