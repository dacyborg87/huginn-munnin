# Evidence Layer Phase 2

## What This Phase Adds

Phase 2 adds the smallest Evidence Builder.

The builder reads the existing Knowledge Graph and Graph Intelligence artifacts, then creates evidence records from current graph relationships.

It creates evidence for architecture weaknesses and links each evidence record to:

- Events
- MITRE techniques
- Attack chains
- Memory entries when available
- Architecture weaknesses
- Defense recommendations

## What This Phase Does Not Add

This phase does not add:

- API endpoints
- Dashboard panels
- Evidence query logic
- Prediction logic
- Autonomous investigation
- Database storage
- Detection rule changes

## Files

```text
core/evidence_builder.py
reports/evidence-builder-output.json
apps/api/tests/test_evidence_builder.py
docs/EVIDENCE_LAYER_PHASE2.md
```

## Inputs

The builder uses existing artifacts:

```text
reports/knowledge-graph.json
reports/graph-intelligence-report.json
core/graph_intelligence.py
core/evidence_schema.py
reports/evidence-index.json
```

## Output

The builder writes:

```text
reports/evidence-builder-output.json
```

The current output contains 3 evidence records, one for each architecture weakness in the current Knowledge Graph.

## How It Works

The builder looks at graph relationships:

- `weakens` links weaknesses to MITRE techniques or attack chains
- `recommends` links defense recommendations to weaknesses
- `relates_to` links events and attack chains to MITRE techniques
- `previously_seen_as` links memory entries to techniques or chains
- `caused_by` can link weaknesses to memory entries

Then it creates one evidence record per architecture weakness.

## Confidence Scoring

The builder uses the existing confidence model from `core/evidence_schema.py`.

Each score includes:

- Source reliability
- Entity correlation
- Repeat observation
- Recency
- Severity alignment

Each evidence record includes a plain-English explanation.

## Example

An evidence record for the post-auth visibility weakness can connect:

```text
Architecture Weakness:
Post-auth activity lacks architectural visibility and response coverage

MITRE Techniques:
T1078 Valid Accounts
T1087 Account Discovery

Attack Chain:
sim-full-lifecycle-001

Recommendations:
Add a post-auth telemetry enrichment layer
Improve post-auth attack surface instrumentation

Memory:
Previously seen post-auth weakness patterns
```

## Explain Like I Am 10

Phase 1 made the shape of proof cards.

Phase 2 starts filling out proof cards automatically from the map.

The map already knows which weak spots, attack tricks, events, memories, and fix ideas are connected. The Evidence Builder reads those strings and makes proof cards that say:

```text
This weak spot matters because these attack tricks, events, memories, and fix ideas connect to it.
```

## Validation

Phase 2 should pass:

```bash
apps/api/.venv/bin/ruff check core/evidence_builder.py apps/api/tests/test_evidence_builder.py
apps/api/.venv/bin/python -m py_compile core/evidence_builder.py apps/api/tests/test_evidence_builder.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 apps/api/.venv/bin/python -m pytest apps/api/tests/test_evidence_builder.py -q
```

The focused graph/API/evidence suite should also continue to pass.
