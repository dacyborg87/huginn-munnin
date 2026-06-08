# Milestone 02: Evidence Layer

## Summary

The Evidence Layer milestone is complete.

Huginn/Munnin can now define evidence records, build evidence from graph intelligence, search existing evidence, expose evidence through the API, and show evidence in the dashboard.

This milestone makes defensive recommendations more trustworthy because findings can point back to supporting proof.

## Completed Components

### Evidence Schema

Location:

```text
core/evidence_schema.py
```

Purpose:

Defines the shape of an evidence record.

Evidence records include:

- evidence ID
- title
- summary
- source type
- source path
- source reference
- timestamp
- related graph entities
- confidence score
- confidence explanation

The schema connects evidence to:

- events
- MITRE techniques
- attack chains
- memory entries
- architecture weaknesses
- defense recommendations

### Evidence Builder

Location:

```text
core/evidence_builder.py
reports/evidence-builder-output.json
```

Purpose:

Creates evidence records from existing graph intelligence relationships.

The builder links architecture weaknesses to supporting facts such as MITRE techniques, related events, memory entries, and defense recommendations.

### Evidence Query Layer

Location:

```text
core/evidence_query.py
reports/evidence-query-output.json
```

Purpose:

Allows Huginn/Munnin to search existing evidence records.

Supported queries:

- evidence by finding ID
- evidence by MITRE technique
- evidence by related weakness
- evidence by recommendation
- evidence by confidence level

The query layer also handles empty results clearly by identifying them as evidence gaps.

### Evidence API

Location:

```text
apps/api/src/huginn_muninn_api/core/evidence_api.py
apps/api/src/huginn_muninn_api/main.py
```

Purpose:

Exposes the Evidence Query Layer through read-only FastAPI endpoints.

Current endpoints:

```text
GET /evidence/summary
GET /evidence/finding/{finding_id}
GET /evidence/mitre/{technique_id}
GET /evidence/weakness/{weakness_id}
GET /evidence/recommendation/{recommendation_id}
GET /evidence/confidence/{level}
```

The API returns evidence records, match counts, and plain-English explanations.

### Evidence Dashboard Panel

Location:

```text
apps/web/app/page.tsx
```

Purpose:

Makes evidence visible in the dashboard.

The panel shows:

- evidence record count
- confidence levels
- sample finding evidence
- related MITRE techniques
- related weaknesses
- related recommendations
- evidence gap explanation
- refresh button

## Validation

Focused graph, API, and evidence tests passed:

```text
42 passed
```

Validated areas:

- Knowledge Graph
- Graph Intelligence
- Graph API
- Evidence Schema
- Evidence Builder
- Evidence Query Layer
- Evidence API

## What The Evidence Layer Proves

The Evidence Layer proves that Huginn/Munnin can move beyond unsupported recommendations.

Before this milestone, the platform could connect graph entities and produce recommendations.

After this milestone, the platform can also show why a finding or recommendation exists.

This matters because a defensive intelligence system must be able to answer:

- What supports this finding?
- Which event is connected to this weakness?
- Which MITRE technique is involved?
- Which recommendation is supported by evidence?
- How confident is the system?
- What happens when no evidence exists?

## Known Limitation

The dashboard runs locally in development mode and returned HTTP 200 during validation.

However, `next build` is still unreliable in the local Homebrew Node/npm environment. The issue appears tied to the local Node/npm toolchain, not the Evidence Layer logic.

Do not treat production web build as fully stabilized until the local Node/npm environment is repaired or replaced with a clean runtime.

## Next Recommended Phase

Recommended next phase:

```text
Evidence-Backed Recommendation Detail View
```

Why:

The Evidence Layer now stores, searches, exposes, and displays proof. The next useful step is to make each recommendation explain itself with supporting evidence.

Expected next work:

- Add a recommendation-focused evidence view
- Show evidence records grouped by recommendation
- Show confidence reasoning beside each recommendation
- Highlight evidence gaps before recommendations are trusted
- Keep the system read-only and explainable

## Explain Like I Am 10

Huginn has ideas.

Muninn remembers things.

The Evidence Layer gives them proof cards.

Each proof card says:

- what happened
- what attack trick it connects to
- what weak spot it supports
- what fix idea it supports
- how sure the system is

Now Huginn can say, "I think this is important, and here is the proof."

If Huginn has no proof, it says, "I do not have proof for that yet."

That is important because guessing is not good enough for security work.

## Explain Like I Am A SOC Analyst

The Evidence Layer adds traceability to Huginn/Munnin's defensive intelligence workflow.

It connects findings and recommendations back to structured evidence records, including MITRE techniques, related events, architecture weaknesses, memory entries, and confidence scoring.

Operational value:

- Findings are easier to validate.
- Recommendations have supporting context.
- Evidence gaps are visible.
- Similar future workflows can cite prior proof.
- The system becomes more useful for investigation notes and incident reporting.

This is not automatic remediation. It is an explainability and traceability layer.

## Explain Like I Am A Hiring Manager

This milestone demonstrates that Huginn/Munnin is evolving from a graph-based prototype into a more credible defensive intelligence platform.

The Evidence Layer shows practical engineering maturity:

- structured data modeling
- confidence scoring
- JSON-backed persistence
- queryable evidence retrieval
- read-only API design
- dashboard integration
- focused automated testing
- clear documentation

The important takeaway is that the platform does not just generate recommendations. It can now preserve and retrieve the evidence used to support those recommendations.

That is a core requirement for security tools used by analysts, engineers, and decision makers.
