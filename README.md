# Huginn/Muninn

Defensive intelligence connecting security telemetry, evidence, context, and analyst decisions.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white) ![Next.js 15](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white) ![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

![Huginn/Muninn dashboard showing live telemetry, evidence panel, and graph intelligence](docs/assets/screenshots/02-huginn-dashboard.png)

Huginn/Muninn ingests security telemetry from multiple sources, normalizes detections into a common `EventRecord` schema, connects findings to MITRE ATT&CK context, and generates evidence records while explicitly tracking evidence gaps.

Unlike a log aggregator or SIEM, evidence gaps are first-class findings rather than ignored failures. Intelligence is graph-connected instead of only tabular, and the dashboard shows both what the system knows and what it cannot confirm.

The platform is built for SOC analyst triage support, detection engineering learning, and demonstrating repeatable multi-source normalization patterns.

## Architecture

Security telemetry moves through a shared normalization, graph, evidence, API, and presentation path.

```text
Security Events (Wazuh · GuardDuty)
        ↓
    Parser Layer
  (EventRecord schema)
        ↓
   Knowledge Graph
  (MITRE · entities · relationships)
        ↓
   Evidence Layer
  (confidence scoring · gap detection)
        ↓
    FastAPI Layer
  (ingestion · intelligence · telemetry APIs)
        ↓
  Next.js Dashboard
  (interactive intelligence panels)
```

Adding a new telemetry source requires a parser and an adapter. The graph, evidence layer, and dashboard require no changes.

## Features

**Multi-Source Ingestion**

`POST /ingest/wazuh` accepts Wazuh alert payloads, while `POST /ingest/guardduty` accepts AWS GuardDuty findings. Both paths normalize source-specific data into `EventRecord`, the contract shared by downstream graph and evidence processing.

**Graph-Connected Intelligence**

The knowledge graph connects events, MITRE ATT&CK techniques, attack chains, architecture weaknesses, memory entries, and defensive recommendations. Graph intelligence queries expose related entities and supporting relationships instead of treating each detection as an isolated row.

**Evidence Layer with Gap Detection**

The evidence layer creates traceable records, assigns confidence scores, and records missing MITRE mappings or supporting context as evidence gaps. Gap detection tells an analyst where a conclusion needs additional telemetry or validation before action is taken.

**Live Telemetry Dashboard**

The Next.js dashboard presents recent telemetry, severity and rule summaries, evidence status, and an interactive intelligence panel. Analysts can select events to inspect MITRE context and linked evidence, while a 30-second refresh cycle keeps the display aligned with the latest accepted report.

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
| `GET /evidence/mitre/{technique_id}` | Evidence for MITRE technique |
| `GET /evidence/summary` | Full evidence index |

## One-Command Demo

The fastest way to see the platform running. Works on Mac and Linux.

```bash
chmod +x demo.sh
./demo.sh
```

The script will:
1. Check that Python 3.11 and Node.js 22 are installed
2. Install Python and Node dependencies if needed
3. Start the FastAPI backend on `http://127.0.0.1:8000`
4. Start the Next.js dashboard on `http://localhost:3000`
5. Wait until the API is healthy
6. Inject a synthetic Wazuh alert (rule `DEMO-60122`, techniques T1110 + T1078)
7. Print exactly what to click next

Press **Ctrl+C** to stop both servers when you are done.

> API logs: `cat /tmp/huginn-api.log` · Dashboard logs: `cat /tmp/huginn-web.log`

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
    "_source": {
      "rule": {
        "id": "550",
        "description": "Integrity checksum changed."
      },
      "timestamp": "2026-06-17T00:00:00Z",
      "agent": {
        "name": "synthetic-host"
      },
      "data": {
        "win": {
          "system": {
            "severityValue": "3"
          }
        }
      }
    }
  }'
```

The dashboard will reflect the ingestion within 30 seconds.

## Testing

Tests favor direct unit calls over `TestClient` to keep asynchronous startup and lifespan behavior isolated. The stable test configuration disables the `anyio` plugin and requires `PYTHONPATH=src` so API modules resolve consistently.

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:anyio \
  --ignore=tests/test_graph_intelligence.py -v
```

120+ tests across ingestion, evidence, graph intelligence, telemetry refresh, and orchestration.

## Project Status

- [x] Knowledge Graph with MITRE ATT&CK mapping
- [x] Evidence Layer with confidence scoring and gap detection
- [x] Wazuh telemetry normalization pipeline
- [x] AWS GuardDuty normalization parser
- [x] POST /ingest/wazuh ingestion endpoint
- [x] POST /ingest/guardduty ingestion endpoint
- [x] Near-live telemetry refresh (30-second polling)
- [x] Interactive intelligence dashboard
- [x] 5-minute hiring manager demo script

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for the full demo walkthrough.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11, FastAPI, asyncio |
| Parsing | Custom `EventRecord` normalization layer |
| Graph | In-memory knowledge graph with relationship traversal |
| Evidence | Custom confidence scoring engine |
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Testing | pytest, direct unit testing pattern |
| Telemetry | Wazuh (endpoint), AWS GuardDuty (cloud) |
| MITRE | ATT&CK technique mapping, static and graph-connected |

## Notes

- Raw Wazuh alert files are not committed to this repository.
- All test fixtures use synthetic data only.
- This repository is intended for cybersecurity portfolio and learning purposes.

## License

[MIT](LICENSE)
