# Evidence Layer Phase 1

## What This Phase Adds

Phase 1 creates the Evidence Data Model foundation.

It adds:

- Evidence record schema
- Evidence source types
- Related entity links
- Explainable confidence scoring
- Sample evidence records
- Unit tests for the schema

It does not add:

- API routes
- Dashboard panels
- Evidence Builder logic
- Evidence Query logic
- Database storage

## Files

```text
core/evidence_schema.py
reports/evidence-index.json
apps/api/tests/test_evidence_schema.py
docs/EVIDENCE_LAYER_PHASE1.md
```

## Evidence Record

An evidence record is one proof card.

Example:

```json
{
  "evidence_id": "evidence:valid-account-post-auth-001",
  "title": "Valid account activity occurred during post-auth phase",
  "source_type": "attack_chain_report",
  "source_path": "reports/attack-chain-analysis.json",
  "source_reference": "attack-chain:sim-full-lifecycle-001"
}
```

## Confidence

Confidence explains how strong the proof is.

The first version uses:

- `low`: 0.00 to 0.39
- `medium`: 0.40 to 0.69
- `high`: 0.70 to 1.00

Each confidence score also stores a calculation and a plain English explanation.

## Explain Like I Am 10

Huginn has a map.

Muninn has memory.

The Evidence Layer gives them proof cards.

Each proof card says:

- What the clue is
- Where the clue came from
- Which map cards it connects to
- How strong the clue is
- Why the clue score makes sense

Phase 1 only creates the proof card shape and a few example cards. Later phases can search the cards, show them in the API, and display them on the dashboard.
