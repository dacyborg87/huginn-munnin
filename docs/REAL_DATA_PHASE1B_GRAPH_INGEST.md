# Real Data Phase 1B: Graph Ingest

## Goal

Take normalized Wazuh `EventRecord` objects and safely add them to the existing Knowledge Graph.

This phase connects parsed real-data events to MITRE technique nodes.

## What Was Added

```text
core/ingest/graph_ingest.py
apps/api/tests/test_graph_ingest.py
reports/real-data-graph-ingest-output.json
docs/REAL_DATA_PHASE1B_GRAPH_INGEST.md
```

## Input

The graph ingest layer accepts:

```python
list[EventRecord]
```

`EventRecord` comes from:

```text
core/ingest/wazuh_parser.py
```

## What It Adds To The Graph

For each event:

1. Add an `Event` node.
2. Add `MITRE Technique` nodes for every MITRE technique on the event.
3. Add `relates_to` relationships between the event and each MITRE technique.

Example:

```text
Event: event:1700000000.12345
relates_to
MITRE Technique: mitre:T1110
```

## Deduplication

The ingest layer safely avoids duplicate graph objects.

It deduplicates:

- Event nodes by event ID
- MITRE Technique nodes by technique ID
- `relates_to` relationships by source and target

## Summary Output

The ingest layer returns:

```json
{
  "events_added": 3,
  "techniques_added": 2,
  "relationships_added": 3,
  "duplicates_skipped": 1,
  "events_without_mitre": 1
}
```

## Sample Report

Sample output is saved to:

```text
reports/real-data-graph-ingest-output.json
```

## What This Phase Does Not Do

This phase does not:

- add API endpoints
- modify the dashboard
- modify the evidence layer
- change graph intelligence behavior
- read Wazuh files directly
- modify detection rules

## Explain Like I Am 10

Phase 1A made clean event cards from Wazuh alerts.

Phase 1B puts those cards onto the map.

If a card says the attack technique is `T1110`, the system also puts a `T1110` card on the map and draws a line between them.

If the same card is already on the map, it does not add it again.

## Why This Matters

This is the first real-data bridge into the Knowledge Graph.

It proves that parsed Wazuh alerts can become graph intelligence inputs without changing the existing graph, API, dashboard, or evidence systems.
