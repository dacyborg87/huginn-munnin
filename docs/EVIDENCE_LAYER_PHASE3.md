# Evidence Layer Phase 3: Evidence Query Layer

## Goal

Phase 3 lets Huginn and Muninn search evidence records that already exist.

This phase does not create new evidence. It does not add API routes. It does not change the dashboard. It only adds a small read-only query layer.

## What Was Added

```text
core/evidence_query.py
reports/evidence-query-output.json
apps/api/tests/test_evidence_query.py
docs/EVIDENCE_LAYER_PHASE3.md
```

## What The Query Layer Reads

The query layer loads evidence from:

```text
reports/evidence-builder-output.json
reports/evidence-index.json
```

It combines the records and removes duplicates by `evidence_id`.

## Supported Queries

### Evidence By Finding ID

Finds evidence connected to a finding, source reference, evidence ID, or related graph entity.

Example:

```python
EvidenceQuery(".").find_by_finding_id(
    "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
)
```

### Evidence By MITRE Technique

Finds evidence linked to a MITRE ATT&CK technique.

Example:

```python
EvidenceQuery(".").find_by_mitre_technique("T1078")
```

### Evidence By Related Weakness

Finds evidence linked to an architecture weakness.

Example:

```python
EvidenceQuery(".").find_by_related_weakness(
    "weakness:15953a2c-3b98-4640-9401-1306f95162e3"
)
```

### Evidence By Recommendation

Finds evidence linked to a defense recommendation.

Example:

```python
EvidenceQuery(".").find_by_recommendation(
    "recommendation:design.post_auth_telemetry_layer"
)
```

### Evidence By Confidence Level

Finds evidence records by confidence level.

Example:

```python
EvidenceQuery(".").find_by_confidence_level("high")
```

## Empty Results

If a query finds nothing, it returns an empty list and a plain-English explanation.

Empty results are important because they show an evidence gap. An evidence gap means Huginn should be careful because it does not yet have proof for that question.

## Sample Output

The sample output report is saved here:

```text
reports/evidence-query-output.json
```

It includes example queries for:

- MITRE technique evidence
- Weakness evidence
- Recommendation evidence
- Confidence level evidence
- Empty-result handling

## Explain Like I Am 10

Think of evidence records like proof cards.

Phase 1 made the shape of a proof card.

Phase 2 created proof cards from the graph.

Phase 3 lets Huginn search the proof cards.

If Huginn asks, "What proof do we have for this attack technique?", the query layer looks through the cards and brings back the matching proof.

If there is no matching proof, it says, "I found no proof for this yet." That is useful because Huginn now knows where the proof is missing.

## What This Unlocks Next

The Evidence Query Layer prepares the system for:

- Evidence API endpoints
- Evidence dashboard panels
- Better recommendation explanations
- Future Prediction Engine support
- Future Autonomous Investigation support

Future systems should use these queries before making strong claims.
