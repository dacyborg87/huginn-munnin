# Real Data Phase 1A: Wazuh Parser

## Goal

Create the smallest safe parser for Wazuh alerts.

This phase converts one raw Wazuh alert JSON dictionary into one normalized internal event record.

## What Was Added

```text
core/ingest/__init__.py
core/ingest/wazuh_parser.py
apps/api/tests/test_wazuh_parser.py
docs/REAL_DATA_PHASE1A_WAZUH_PARSER.md
```

## What The Parser Accepts

Input:

```python
dict
```

The dictionary should look like a Wazuh alert, but missing fields are allowed.

Example:

```json
{
  "id": "1700000000.12345",
  "timestamp": "2026-06-08T14:22:31.000Z",
  "agent": {
    "name": "windows-endpoint-01"
  },
  "rule": {
    "id": "60122",
    "level": 10,
    "description": "Multiple Windows logon failures",
    "mitre": {
      "id": ["T1110", "T1078"]
    }
  }
}
```

## Normalized EventRecord

Output:

```python
EventRecord(
    id="1700000000.12345",
    timestamp="2026-06-08T14:22:31.000Z",
    source="wazuh",
    rule_id="60122",
    description="Multiple Windows logon failures",
    host="windows-endpoint-01",
    mitre_techniques=["T1110", "T1078"],
    severity="high",
)
```

## Extracted Fields

The parser extracts:

- alert ID
- timestamp
- rule ID
- rule description
- agent name
- MITRE technique IDs from `rule.mitre.id`
- severity level

## Severity Mapping

Wazuh rule levels are mapped to simple internal severity labels:

| Wazuh Level | Normalized Severity |
|---:|---|
| 12 and higher | critical |
| 7 to 11 | high |
| 4 to 6 | medium |
| 0 to 3 | low |

If the rule level is not numeric, the parser keeps it as text.

## Missing Field Handling

Missing fields are allowed.

If a field is missing:

- string-like fields become `None`
- MITRE technique IDs become an empty list
- source is always `wazuh`

## What This Phase Does Not Do

This phase does not:

- modify the Knowledge Graph
- ingest files
- write reports
- add API endpoints
- modify the dashboard
- modify evidence logic
- modify Wazuh rules

## Explain Like I Am 10

Wazuh sends a big alert message.

The parser reads that message and copies the important parts onto a smaller card.

The card says:

- alert ID
- time
- rule number
- what happened
- computer name
- attack technique
- how serious it is

If Wazuh forgets a field, the parser does not crash. It just leaves that part blank.

## Why This Matters

This is the first step toward real security data.

Before Huginn/Muninn can build graphs or evidence from real Wazuh alerts, it needs a safe way to turn raw alerts into a clean internal shape.

Phase 1A creates that clean shape.
