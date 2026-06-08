# Evidence Layer Phase 4: Evidence API

## Goal

Phase 4 exposes the existing Evidence Query Layer through read-only API endpoints.

This phase does not create new evidence. It does not change the dashboard. It does not add a database. It only lets other parts of Huginn/Muninn ask for evidence through HTTP.

## What Was Added

```text
apps/api/src/huginn_muninn_api/core/evidence_api.py
apps/api/tests/test_evidence_api.py
docs/EVIDENCE_LAYER_PHASE4.md
```

Updated:

```text
apps/api/src/huginn_muninn_api/main.py
```

## Data Sources

The API reads existing JSON evidence only:

```text
reports/evidence-builder-output.json
reports/evidence-index.json
```

## Endpoints

### Evidence Summary

```text
GET /evidence/summary
```

Returns total evidence records, confidence counts, source type counts, and the current records.

### Evidence By Finding

```text
GET /evidence/finding/{finding_id}
```

Returns evidence connected to a finding, source reference, evidence ID, or graph entity.

### Evidence By MITRE Technique

```text
GET /evidence/mitre/{technique_id}
```

Example:

```text
GET /evidence/mitre/T1078
```

Returns evidence linked to the MITRE technique.

### Evidence By Weakness

```text
GET /evidence/weakness/{weakness_id}
```

Returns evidence linked to an architecture weakness.

### Evidence By Recommendation

```text
GET /evidence/recommendation/{recommendation_id}
```

Returns evidence linked to a defense recommendation.

### Evidence By Confidence Level

```text
GET /evidence/confidence/{level}
```

Example:

```text
GET /evidence/confidence/high
```

Returns evidence records with the requested confidence level.

## Response Shape

Most endpoints return:

```json
{
  "entity_searched": "T1078",
  "query_type": "mitre_technique",
  "evidence_records": [],
  "match_count": 0,
  "explanation": "Plain-English explanation."
}
```

## Empty Results

If no evidence matches, the API returns:

```json
{
  "evidence_records": [],
  "match_count": 0,
  "explanation": "No evidence records matched ... Huginn should treat this as an evidence gap, not as proof that the activity is safe."
}
```

This is important because missing proof is still useful information.

## Run Locally

Start the API:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/uvicorn huginn_muninn_api.main:app --reload --host 127.0.0.1 --port 8000
```

Example checks:

```bash
curl http://127.0.0.1:8000/evidence/summary
curl http://127.0.0.1:8000/evidence/mitre/T1078
curl http://127.0.0.1:8000/evidence/confidence/high
```

## Explain Like I Am 10

Huginn already has proof cards.

Phase 3 taught Huginn how to search the proof cards.

Phase 4 gives Huginn a window where other tools can ask, "Show me the proof for this thing."

If proof exists, the API gives it back.

If proof does not exist, the API says, "I do not have proof for that yet."

## What This Unlocks Next

The Evidence API prepares the system for:

- Evidence dashboard panels
- Recommendation pages with proof
- Investigation workflows that cite evidence
- Future prediction logic that checks proof before making claims
