# Huginn/Muninn 5-Minute Demo Script

This script is designed for a short hiring manager demonstration using only
synthetic, sanitized telemetry.

## 1. Prerequisites

Python environment setup:

```bash
cd apps/api
.venv/bin/python -m pip install -e ".[dev]"
```

Node 22 PATH setup:

```bash
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
```

Start the API:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/uvicorn huginn_muninn_api.main:app --reload --host 127.0.0.1 --port 8000
```

Start the dashboard:

```bash
cd apps/web
npm run dev
```

Verify both are running:

```bash
curl http://localhost:8000/health
curl -I http://localhost:3000
```

Expected API health response:

```json
{
  "status": "ok",
  "system": "huginn-muninn"
}
```

## 2. Step-by-Step Demo Sequence

### Step 1: Open Dashboard, Show Existing Telemetry Panels

Open:

```text
http://localhost:3000
```

Show:

- Live Telemetry Intelligence
- Recent Security Events
- Severity Breakdown
- Top Rule IDs
- Top Agents

Talking point:

This shows that Huginn/Muninn is not only storing alerts, it is organizing
telemetry into analyst-facing operational summaries.

### Step 2: Show The Evidence Panel And Evidence Gaps Panel

Show:

- Evidence summary
- Evidence records
- Evidence gaps
- Confidence levels

Talking point:

This demonstrates evidence-backed detection engineering where findings are
tracked with confidence and missing context is treated as a first-class gap.

### Step 3: POST A Sanitized Wazuh Alert Via Curl

Run this synthetic alert ingestion command:

```bash
curl -X POST http://localhost:8000/ingest/wazuh \
  -H "Content-Type: application/json" \
  -d '{
    "id": "demo-0001",
    "timestamp": "2026-06-17T15:00:00.000Z",
    "agent": {
      "name": "demo-endpoint-01"
    },
    "rule": {
      "id": "DEMO-60122",
      "level": 10,
      "description": "Synthetic repeated authentication failure pattern",
      "mitre": {
        "id": ["T1110", "T1078"]
      }
    }
  }'
```

Expected response:

```json
{
  "records_received": 1,
  "records_parsed": 1,
  "records_skipped": 0,
  "events_added": 1,
  "techniques_added": 2,
  "relationships_added": 2,
  "duplicates_skipped": 0,
  "evidence_records_created": 1,
  "evidence_gaps_created": 0,
  "status": "accepted",
  "message": "Ingestion complete. Dashboard will refresh within 30 seconds."
}
```

Talking point:

This proves the platform has a controlled runtime ingestion path, not just a
static report viewer.

### Step 4: Show GET /dashboard/last-updated Response

Run:

```bash
curl http://localhost:8000/dashboard/last-updated
```

Show:

- `last_successful_reload`
- `last_reload_error`
- `source_path`
- `cache_status`

Talking point:

This shows the dashboard telemetry layer tracks report freshness and preserves
the last good cache if a reload fails.

### Step 5: Wait 30 Seconds, Show Dashboard Refresh

Wait:

```text
30 seconds
```

Then refresh or revisit:

```text
http://localhost:3000
```

Show the new synthetic event or updated telemetry summary.

Talking point:

This demonstrates near-live behavior using a controlled polling interval instead
of forcing a restart.

### Step 6: Click The New Event In Recent Events Panel

Click the new synthetic event row under Recent Security Events.

Talking point:

This shows the dashboard is interactive and can pivot from a telemetry summary
into event-level intelligence.

### Step 7: Walk Through The Intelligence Detail Panel

Show:

- Event summary
- MITRE technique
- Evidence record
- Evidence gap
- Plain-English explanation

Talking point:

This demonstrates that Huginn/Muninn can connect alert context, MITRE mapping,
evidence, and gaps into a readable analyst workflow.

## 3. Talking Points For Each Step

1. Existing telemetry panels demonstrate operational visibility across events,
   severities, rules, agents, evidence, and gaps.
2. Evidence panels show that findings are backed by traceable supporting records.
3. Runtime Wazuh ingestion proves the system accepts live-style telemetry through
   a controlled API entry point.
4. Last-updated status proves the dashboard can explain freshness and cache
   health.
5. The 30-second refresh demonstrates near-live behavior without restarting the
   API.
6. Clickable event rows show analyst-oriented investigation workflow.
7. The detail panel ties together MITRE context, evidence, gaps, and plain
   explanation.

## 4. Known Demo Environment Notes

- Use Node 22 with:

  ```bash
  export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
  ```

- Use `PYTHONPATH=src` when starting or testing the API from `apps/api`.
- Report refresh is 30 seconds, not instant.
- Runtime graph and evidence persist in `reports/knowledge-graph.json` and `reports/evidence-index.json`. Restarting the API with the same files preserves ingested alerts; replaying an alert ID adds no duplicate event. See the README restart walkthrough. Keep `reports/` and `core/patterns/` writable and on persistent storage; do not regenerate sample artifacts to restart the demo.
- Do not use real hostnames, IPs, usernames, or raw alert logs in screenshots.

## 5. What To Say If Something Goes Wrong

API not running:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/uvicorn huginn_muninn_api.main:app --reload --host 127.0.0.1 --port 8000
```

Dashboard shows no new event:

The dashboard reads a cached telemetry report and refreshes every 30 seconds, so
wait for the next polling cycle or click the refresh control.

Intelligence panel shows empty MITRE:

That means the event did not have a usable MITRE mapping. Huginn/Muninn treats
that as a detection context gap instead of hiding it.
