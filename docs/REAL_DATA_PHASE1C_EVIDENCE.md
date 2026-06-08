# Real Data Phase 1C: Evidence From Ingested Wazuh Events

## Goal

Generate Evidence Layer records from normalized Wazuh `EventRecord` data.

This phase connects real-data Wazuh alerts to the existing Evidence Layer without adding APIs, dashboard changes, databases, or schema redesigns.

## What Was Added

```text
core/ingest/real_data_evidence.py
apps/api/tests/test_real_data_evidence.py
reports/real-data-evidence-output.json
docs/REAL_DATA_PHASE1C_EVIDENCE.md
```

## Inputs

The module accepts:

```python
list[EventRecord]
```

`EventRecord` comes from:

```text
core/ingest/wazuh_parser.py
```

## Outputs

The module creates existing Evidence Layer records:

```text
EvidenceRecord
```

Sample output is saved to:

```text
reports/real-data-evidence-output.json
```

## What Each Evidence Record Links

Each evidence record links:

- Wazuh event ID
- Wazuh rule ID
- severity
- MITRE techniques when available
- related graph Event node
- related graph MITRE Technique nodes when available

## Confidence Scoring

The module uses the existing evidence confidence model:

- source reliability
- MITRE mapping presence
- rule context
- host context
- severity alignment

Events with MITRE mappings can receive higher confidence.

Events without MITRE mappings are treated as evidence gaps and receive low confidence.

## Evidence Gaps

If a Wazuh event has no MITRE techniques, the system still creates an evidence record.

That record explains that the event exists, but Huginn does not yet have enough MITRE context to connect it strongly to attack behavior.

This is useful because missing context is still important security information.

## What This Phase Does Not Do

This phase does not:

- add API endpoints
- modify dashboard code
- change the Wazuh parser
- redesign the evidence schema
- modify existing evidence builder logic
- write to the production knowledge graph file
- modify detection rules

## Explain Like I Am 10

Phase 1A made clean Wazuh alert cards.

Phase 1B put those cards on the map.

Phase 1C makes proof cards from those alerts.

If a Wazuh alert says `T1110`, Huginn can make a proof card that says:

"This alert is connected to this attack technique."

If the alert has no attack technique, Huginn makes a different proof card that says:

"I saw the alert, but I do not have enough attack context yet."

That is called an evidence gap.

## Why This Matters

This phase proves the first real-data evidence workflow:

```text
Wazuh alert
-> normalized EventRecord
-> Knowledge Graph event and MITRE relationship
-> EvidenceRecord
```

It is the first step toward evidence-backed analysis from real SOC data.
