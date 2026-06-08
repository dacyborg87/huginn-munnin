# Evidence Layer Phase 5: Evidence Dashboard Panel

## Goal

Phase 5 makes the existing Evidence API visible in the Huginn/Munnin dashboard.

This phase does not add API endpoints. It does not change the evidence schema. It does not change core evidence logic. It only adds a small read-only panel to the existing dashboard.

## What Was Updated

```text
apps/web/app/page.tsx
docs/EVIDENCE_LAYER_PHASE5.md
docs/DEPLOYMENT_AND_TESTING_PLAN.md
```

## Existing API Endpoints Used

```text
GET /evidence/summary
GET /evidence/finding/{finding_id}
GET /evidence/mitre/{technique_id}
GET /evidence/weakness/{weakness_id}
GET /evidence/recommendation/{recommendation_id}
GET /evidence/confidence/{level}
```

## Dashboard Content

The Evidence panel shows:

- Evidence record count
- Confidence level counts
- Sample finding evidence
- Supporting facts
- Related MITRE techniques
- Related weaknesses
- Related recommendations
- Evidence gap example
- Refresh Evidence button

## How It Works

The dashboard fetches data from the Evidence API and displays the returned JSON.

The panel does not calculate evidence by itself. Huginn/Munnin keeps the evidence logic in the API and core modules.

## Empty Evidence Handling

The panel includes an evidence gap example.

If the API returns no matching evidence, the panel shows the plain-English explanation from the API.

This matters because "no proof found" is still useful. It tells Huginn that the system should be careful before making a strong claim.

## Run Locally

Start the API:

```bash
cd apps/api
.venv/bin/uvicorn --app-dir src huginn_muninn_api.main:app --host 127.0.0.1 --port 8000
```

Start the dashboard:

```bash
cd apps/web
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
npm run dev
```

Open:

```text
http://127.0.0.1:3000/
```

## Explain Like I Am 10

Huginn has proof cards.

The Evidence API can search the proof cards.

The dashboard now shows the proof cards on the screen.

If Huginn has proof, the panel shows it.

If Huginn does not have proof, the panel says there is an evidence gap.

## What This Unlocks Next

This prepares the platform for:

- Evidence-focused dashboard workflows
- Investigation pages that cite proof
- Recommendations that show supporting facts
- Future Prediction Engine checks that ask for evidence before making claims
