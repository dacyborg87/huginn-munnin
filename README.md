# Huginn/Muninn

Defensive intelligence dashboard connecting security telemetry, MITRE ATT&CK context, and evidence-backed analysis.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white) ![Next.js 15](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

![Live Telemetry Intelligence panel showing a synthetic authentication alert, severity breakdown, evidence count, and evidence gaps](docs/assets/screenshots/live-telemetry-panel.png)

## How It Works

Security alerts from Wazuh (endpoint) or AWS GuardDuty (cloud) are sent to the FastAPI backend via a `POST` request. The backend normalizes each alert into a common `EventRecord` format, adds it to a JSON-backed Security Knowledge Graph connected to MITRE ATT&CK techniques, and persists an evidence record with a confidence score before acknowledging ingestion. If a required piece of context is missing — such as a MITRE mapping or a defensive recommendation — the system records that gap explicitly rather than ignoring it. The Next.js dashboard polls the backend every 10–30 seconds and displays the current telemetry, severity breakdown, evidence counts, and any open gaps.

**Huginn** is the thought engine — it routes incoming requests, classifies intent, and coordinates the analysis pipeline.  
**Muninn** is the memory engine — it stores event history, reasoning patterns, and outcome records across the session.

## One-Command Demo

```bash
chmod +x demo.sh
./demo.sh
```

The script checks dependencies, starts both servers, waits until the API is healthy, injects a synthetic Wazuh alert, and tells you exactly what to look at. Press **Ctrl+C** to stop.

> Logs: `cat /tmp/huginn-api.log` · `cat /tmp/huginn-web.log`

## What Is Real vs. Synthetic

| Item | Status |
| --- | --- |
| FastAPI backend with 26 endpoints | Real — runs locally |
| Wazuh alert normalization pipeline | Real — parses alert JSON into `EventRecord` |
| AWS GuardDuty normalization parser | Real — same normalization path |
| JSON-backed Security Knowledge Graph | Real graph structure, seeded with **synthetic sample data**, plus persisted runtime alerts |
| MITRE ATT&CK technique mappings (T1078, T1087, T1110, T1046) | Real technique IDs, connected to **synthetic lab events** |
| Evidence records and confidence scores | Real scoring logic, applied to **synthetic events** |
| Evidence gap detection | Real — gaps are recorded when MITRE mapping or recommendation is missing |
| Live telemetry dashboard (10s/30s refresh) | Real polling, reading from local report files |
| Security events in the dashboard | Mix of synthetic pipeline events and the injected demo alert |
| `POST /ingest/wazuh` and `POST /ingest/guardduty` | Real endpoints — merge graph and evidence into local JSON storage |
| Wazuh detection rules in `detection-engine/` | Real rule syntax, written for a lab environment — not deployed to a live Wazuh instance |
| Raw Wazuh alert log files | **Not included** — no real host logs are committed to this repository |

## Dashboard Panels

![Graph Intelligence panel showing 43 nodes, 42 relationships, and top connected MITRE techniques](docs/assets/screenshots/graph-intelligence-panel.png)

The dashboard is a single-page Next.js application with the following panels, all populated from the running API:

- **Live Telemetry Intelligence** — severity breakdown, recent security events, top rule IDs, top agents, evidence summary, and evidence gaps
- **Graph Intelligence** — knowledge graph summary (total nodes and relationships), top connected entities, MITRE technique connections, architecture weaknesses, and defensive recommendations
- **Evidence** — full evidence index with confidence levels
- **Conversation** — command input routed through the Huginn engine (rule-based intent classification, no language model)
- **Decision Graph / Reasoning Intelligence** — records of path decisions and reasoning patterns from the current session
- **Learning Loop** — outcome records written during the session
- **System Layers** — live status of each subsystem (Huginn, Muninn, Voice, SOC)
- **Security Analysis** — keyword-based log scanner that maps suspicious terms to MITRE tactics

![Evidence Gaps panel and System Layers showing Huginn online, Muninn online, Voice planned, and SOC scaffolded](docs/assets/screenshots/evidence-gaps-panel.png)

## Current Limitations

- Runtime Wazuh/GuardDuty ingestion persists the Security Knowledge Graph to `reports/knowledge-graph.json` and evidence to `reports/evidence-index.json`; graph counts are published to `core/patterns/knowledge-graph-summary.json`. API restarts preserve these files. Keep these directories on writable, persistent local storage (including when running in containers). Deleting the checkout, replacing it with a fresh deployment, or regenerating sample artifacts can erase runtime data.
- JSON storage uses a shared macOS/Linux file lock around ingestion and atomic, fsynced file replacements. It rewrites whole artifacts and is intended for a local demo, not distributed/high-volume ingestion. Graph, summary, and evidence are separate writes, not a multi-file transaction: interrupted or failed requests may partially persist and should be retried with the same alert IDs. Accepted requests need no shutdown flush. The telemetry report shows the latest batch, not the complete persisted history.
- Standalone `KnowledgeGraph()` instances remain in-memory until explicitly saved. Runtime ingestion uses JSON regardless of Muninn's `persistence_backend` setting; evidence queries prefer the persisted index over stale generated records with the same ID.
- Muninn's reasoning memory (chat memory records, outcome history, learned path weights, reasoning patterns, and the full system event log) can now optionally persist to Postgres across restarts — set `persistence_backend=postgres` and run `docker compose up -d postgres`. The default remains in-memory (matching every prior milestone), so this is opt-in, not automatic. See [docs/MUNINN_PERSISTENCE.md](docs/MUNINN_PERSISTENCE.md).
- Intelligence is rule-based and graph-based. There is no machine learning, no language model, and no external AI API call anywhere in the running code.
- The Conversation panel accepts text input but responds with template strings, not generated analysis.
- Wazuh and GuardDuty ingestion accepts JSON payloads directly. There is no live connection to a running Wazuh instance or AWS account.
- The SOC layer (Wazuh + Suricata) is scaffolded — the detection rules exist, but the full pipeline to a live sensor is not wired.
- No authentication or access control has been implemented.
- ChromaDB in `docker-compose.yml` remains unused by the current application — it is a placeholder for future vector-search work, out of scope for this milestone.

## What I Learned

- How to design a normalization layer (`EventRecord`) so that multiple detection sources — Wazuh, GuardDuty — can share a single downstream pipeline without requiring changes to the graph or evidence logic
- How MITRE ATT&CK technique IDs connect to real detection patterns, and why gap detection (tracking what you *cannot* confirm) matters as much as what you can
- How to build a knowledge graph from scratch without a graph database — using in-memory nodes, relationships, and traversal queries backed by JSON
- How to structure a FastAPI application with a clean separation between ingestion, intelligence, and telemetry layers, each independently testable
- How to wire a Next.js frontend to a live backend using polling intervals, stable `useCallback` dependencies, and graceful stale-data fallbacks
- How to write tests that exercise real behavior rather than mocking away the logic being tested, including a persistence "restart test" that proves state survives independent process/store creation rather than asserting a row exists in a table

## Architecture

```mermaid
flowchart TD
    A["Security Events\nWazuh · GuardDuty"] --> B["Parser Layer\nEventRecord schema"]
    B --> C["Knowledge Graph\nMITRE · entities · relationships"]
    C --> D["Evidence Layer\nconfidence scoring · gap detection"]
    D --> E["FastAPI\ningestion · graph · evidence · telemetry"]
    E --> F["Next.js Dashboard\nLive Telemetry · Graph Intelligence · Evidence"]
```

Adding a new telemetry source requires a parser and an ingest adapter. The graph, evidence layer, and dashboard require no changes.

## API Reference

| Endpoint | Description |
| --- | --- |
| `POST /ingest/wazuh` | Accept Wazuh alert payload |
| `POST /ingest/guardduty` | Accept GuardDuty finding payload |
| `GET /dashboard/summary` | Telemetry summary |
| `GET /dashboard/events` | Recent security events |
| `GET /dashboard/evidence` | Evidence summary |
| `GET /dashboard/last-updated` | Cache and reload status |
| `GET /graph/summary` | Knowledge graph summary |
| `GET /graph/related/{entity_id}` | Related graph entities |
| `GET /graph/weaknesses/{entity_id}` | Connected architecture weaknesses |
| `GET /graph/recommendations/{technique_id}` | Defensive recommendations for a technique |
| `GET /evidence/mitre/{technique_id}` | Evidence for a MITRE technique |
| `GET /evidence/summary` | Full evidence index |

## Quick Start

**Requirements:** Python 3.11 or higher · Node.js 22

### Backend

```bash
cd apps/api
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
PYTHONPATH=src uvicorn huginn_muninn_api.main:app --reload --host 127.0.0.1
curl http://localhost:8000/health
```

### Dashboard

> **Mac (Homebrew) only:** if Node 22 is not your default, run this first:
> `export PATH="/opt/homebrew/opt/node@22/bin:$PATH"`
>
> On Linux or Windows, install Node 22 from [nodejs.org](https://nodejs.org) and skip this step.

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:3000`.

### Ingest a test alert

```bash
curl -X POST http://localhost:8000/ingest/wazuh \
  -H "Content-Type: application/json" \
  -d '{
    "id": "demo-0001",
    "timestamp": "2026-06-17T15:00:00.000Z",
    "agent": { "name": "demo-endpoint-01" },
    "rule": {
      "id": "DEMO-60122",
      "level": 10,
      "description": "Synthetic repeated authentication failure pattern",
      "mitre": { "id": ["T1110", "T1078"] }
    }
  }'
```

The dashboard will reflect the ingestion within 30 seconds. Reusing an already ingested alert ID returns `events_added: 0`; graph entities and evidence IDs are deduplicated across restarts.

### Verify persistence across an API restart

After posting the Wazuh alert above, optionally add a synthetic GuardDuty finding:

```bash
curl -f -X POST http://localhost:8000/ingest/guardduty \
  -H 'Content-Type: application/json' \
  -d '{"id":"demo-guardduty-0001","type":"Trojan:EC2/BlackholeTraffic","severity":8,"createdAt":"2026-06-17T15:00:00Z"}'
```

Stop and restart the API with the same checkout and files, using the backend command above. If using `./demo.sh`, stop with Ctrl+C and rerun it; its repeated `demo-0001` injection should add zero events. Do not regenerate the sample graph or evidence index between runs.

```bash
curl -f http://localhost:8000/graph/related/event:demo-0001
curl -f http://localhost:8000/evidence/finding/event:demo-0001
curl -f http://localhost:8000/graph/related/event:demo-guardduty-0001
curl -f http://localhost:8000/evidence/finding/event:demo-guardduty-0001
```

Expect connected MITRE techniques and one event evidence record per finding both before and after restart. Repost either payload to verify deduplication. No Postgres setup is required for this check.

## Testing

Most tests use direct unit calls to keep startup and lifespan behavior isolated; `test_api.py` and the persistence integration tests use `TestClient`/a live event loop directly instead. The `anyio` plugin is disabled and `PYTHONPATH=src` is required.

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:anyio -v
```

Tests cover ingestion, evidence, graph intelligence, telemetry refresh, orchestration, and persistence. Security storage restart tests run real HTTP routes in independent Python processes, exit without shutdown hooks, and verify both sources remain queryable and deduplicated. Run the focused suite from `apps/api`:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_ingest_persistence.py tests/test_json_persistence.py tests/test_evidence_query.py -q
```

Postgres-backed tests self-skip unless `TEST_DATABASE_URL` is set:

```bash
docker compose up -d postgres
TEST_DATABASE_URL=postgresql://muninn:muninn@localhost:5432/muninn \
  PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:anyio -v
```

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11, FastAPI, asyncio |
| Parsing | Custom `EventRecord` normalization layer |
| Graph | JSON-backed runtime knowledge graph with relationship traversal; standalone instances remain in-memory |
| Evidence | Custom confidence scoring and gap detection engine |
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Testing | pytest: 198 passed, 12 skipped; unit and HTTP restart/integration tests |
| Persistence | Security graph/evidence: local JSON; Muninn reasoning: opt-in asyncpg (Postgres), in-memory by default |
| Telemetry sources | Wazuh (endpoint), AWS GuardDuty (cloud) |
| MITRE | ATT&CK technique mapping, graph-connected |

## Project Status

- [x] Knowledge graph with MITRE ATT&CK mapping
- [x] Evidence layer with confidence scoring and gap detection
- [x] Wazuh alert normalization pipeline
- [x] AWS GuardDuty normalization parser
- [x] Runtime ingestion via `POST /ingest/wazuh` and `POST /ingest/guardduty`
- [x] Near-live telemetry dashboard (10s/30s polling)
- [x] Graph intelligence queries (related entities, weaknesses, recommendations)
- [x] Evidence gap detection as first-class findings
- [x] One-command demo script
- [x] Muninn reasoning-memory persistence (opt-in Postgres backend for memory, outcomes, learned weights, reasoning patterns, event log — see [docs/MUNINN_PERSISTENCE.md](docs/MUNINN_PERSISTENCE.md))
- [x] Persistent Security Knowledge Graph and evidence index (local JSON, independent of Muninn reasoning memory)
- [ ] Live Wazuh API connection (planned)
- [ ] Voice interface — Hey Huginn (planned)

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for the full demo walkthrough.

## Notes

- Raw Wazuh alert log files are not committed to this repository.
- All test fixtures and graph seed data use synthetic data only.
- `docker-compose.yml` provisions Postgres (now used, opt-in, by Muninn's persistence layer — see [docs/MUNINN_PERSISTENCE.md](docs/MUNINN_PERSISTENCE.md)) and ChromaDB (still unused, placeholder for future vector-search work). Neither is required to run the demo — Muninn defaults to in-memory, while runtime security graph/evidence use local JSON.
- This project is a cybersecurity portfolio and learning exercise. It is not production-ready and has no authentication.
- `docs/architecture.md` describes the long-term intended architecture, not the current implemented state.

## License

[MIT](LICENSE)
