# Deployment and Testing Plan

This guide explains how to run, test, and use Huginn/Munnin locally.

Think of the system like this:

- Huginn is the thinker.
- Munnin is the memory.
- Reports are the notebook.
- The Knowledge Graph is the map that connects the notebook pages.

## Before You Start

Run commands from the repository root:

```bash
cd /Users/kingkilo/Documents/munnin
```

Use the API virtual environment:

```bash
apps/api/.venv/bin/python --version
```

Expected output:

```text
Python 3.11.x
```

If the environment is missing, recreate it:

```bash
python3.11 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -e 'apps/api[dev]'
```

## Mode 1: Local Sample-Data Mode

Use this mode when you want to test the intelligence system without connecting
real Wazuh, Sysmon, Suricata, or auditd data.

### Use Existing Sample Reports

The repository already contains sample report data in:

```text
reports/
core/patterns/
```

Important files:

```text
reports/soc-events.jsonl
reports/attack-chain-analysis.json
reports/security-architecture-weaknesses.json
reports/defense-design-recommendations.json
core/patterns/strategic-memory.json
```

These files are enough to build the Knowledge Graph.

### Generate Sample Alerts

If you want to append a few simple sample events, run:

```bash
apps/api/.venv/bin/python - <<'PY'
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource

bus = SocEventBus(".")

bus.ingest_lab_event(
    {"description": "sample password spray from Kali", "target": "windows-lab-01"},
    lab_id="sample-local-001",
    attack_step="password_spray",
    mitre_mapping={
        "tactic": "Credential Access",
        "technique_id": "T1110",
        "technique_name": "Brute Force",
    },
    severity=EventSeverity.INFO,
)

bus.ingest_detection_alert(
    EventSource.WAZUH,
    {"rule": "sample repeated failed logon", "attempts": 12},
    detection_name="SOC-WIN-AUTH-BRUTEFORCE-SAMPLE",
    mitre_mapping={
        "tactic": "Credential Access",
        "technique_id": "T1110",
        "technique_name": "Brute Force",
    },
    severity=EventSeverity.HIGH,
    normalized_context={"target_host": "windows-lab-01", "target_account": "lab.user"},
)

print("sample events written to reports/soc-events.jsonl")
PY
```

Expected output:

```text
sample events written to reports/soc-events.jsonl
```

Like you are 10:

This adds a few pretend security clues to Munnin's notebook.

### Create the Knowledge Graph

Run:

```bash
apps/api/.venv/bin/python -c 'from core.graph_context_builder import GraphContextBuilder; GraphContextBuilder().build(persist=True); print("knowledge graph created")'
```

Expected output:

```text
knowledge graph created
```

Expected files:

```text
reports/knowledge-graph.json
core/patterns/knowledge-graph-summary.json
```

### Run Graph Intelligence

Run:

```bash
apps/api/.venv/bin/python -c 'from core.graph_intelligence import write_sample_report; write_sample_report(); print("graph intelligence report created")'
```

Expected output:

```text
graph intelligence report created
```

Expected file:

```text
reports/graph-intelligence-report.json
```

### Verify Knowledge Graph Output

Run:

```bash
apps/api/.venv/bin/python - <<'PY'
import json
from pathlib import Path

path = Path("reports/knowledge-graph.json")
data = json.loads(path.read_text())

print("nodes:", len(data.get("nodes", [])))
print("relationships:", len(data.get("relationships", [])))
print("has_nodes:", bool(data.get("nodes")))
print("has_relationships:", bool(data.get("relationships")))
PY
```

Expected output should look like:

```text
nodes: 43
relationships: 42
has_nodes: True
has_relationships: True
```

Exact numbers may change if you add more sample events.

### Verify Graph Intelligence Output

Run:

```bash
apps/api/.venv/bin/python - <<'PY'
import json
from pathlib import Path

path = Path("reports/graph-intelligence-report.json")
data = json.loads(path.read_text())
questions = data.get("questions", {})

print("has_related_entities:", bool(questions.get("related_entities")))
print("has_connected_weaknesses:", bool(questions.get("connected_weaknesses")))
print("has_recommendations:", bool(questions.get("recommendations_for_technique")))
print("has_similar_incidents:", bool(questions.get("similar_incidents")))
PY
```

Expected output:

```text
has_related_entities: True
has_connected_weaknesses: True
has_recommendations: True
has_similar_incidents: True
```

## Mode 2: Home Lab Mode

Use this mode when you want Wazuh, Sysmon-style, Suricata, auditd, or lab
simulation data to feed Munnin.

### How Alerts Feed Into the System

Sensors stay separate from intelligence.

The intended flow is:

```text
Wazuh / Sysmon / Suricata / auditd
-> normalized SOC event
-> core/event_bus.py
-> reports/soc-events.jsonl
-> Knowledge Graph
-> Graph Intelligence report
```

Like you are 10:

Sensors are the eyes. The event bus is the mailbox. Reports are the notebook.
The graph is the map.

### Files and Folders Involved

Sensor and lab sources:

```text
detection-engine/
labs/
```

Intelligence and routing:

```text
core/event_schema.py
core/event_bus.py
core/context_builder.py
core/graph_context_builder.py
core/knowledge_graph.py
core/graph_intelligence.py
```

Memory and output:

```text
reports/
core/patterns/
```

### Example Wazuh-Style Alert Ingestion

Run:

```bash
apps/api/.venv/bin/python - <<'PY'
from core.event_bus import SocEventBus
from core.event_schema import EventSeverity, EventSource

bus = SocEventBus(".")

bus.ingest_detection_alert(
    EventSource.WAZUH,
    {
        "rule_id": "5710",
        "description": "sshd brute force attempt",
        "source_ip": "10.10.10.50",
    },
    detection_name="SOC-LINUX-SSH-BRUTEFORCE-SAMPLE",
    mitre_mapping={
        "tactic": "Credential Access",
        "technique_id": "T1110",
        "technique_name": "Brute Force",
    },
    severity=EventSeverity.HIGH,
    normalized_context={
        "source_ip": "10.10.10.50",
        "target_host": "linux-lab-01",
    },
)

print("wazuh-style alert written")
PY
```

Expected output:

```text
wazuh-style alert written
```

### What Outputs To Check

After ingesting home lab events, rebuild the graph:

```bash
apps/api/.venv/bin/python -c 'from core.graph_context_builder import GraphContextBuilder; GraphContextBuilder().build(persist=True)'
apps/api/.venv/bin/python -c 'from core.graph_intelligence import write_sample_report; write_sample_report()'
```

Check:

```text
reports/soc-events.jsonl
reports/knowledge-graph.json
reports/graph-intelligence-report.json
core/patterns/knowledge-graph-summary.json
```

Useful checks:

```bash
tail -n 5 reports/soc-events.jsonl
```

```bash
apps/api/.venv/bin/python - <<'PY'
import json
print(json.dumps(json.load(open("core/patterns/knowledge-graph-summary.json")), indent=2))
PY
```

Expected result:

- `reports/soc-events.jsonl` contains the newest normalized alerts.
- `reports/knowledge-graph.json` contains nodes and relationships.
- `reports/graph-intelligence-report.json` contains graph questions and answers.
- `core/patterns/knowledge-graph-summary.json` shows total nodes, total relationships, and top connected entities.

## Mode 3: Dashboard/API Mode

Use this mode when you want to run the Huginn/Munnin API and web dashboard.

### Start the API

From the repository root:

```bash
cd apps/api
.venv/bin/uvicorn huginn_muninn_api.main:app --reload --host 127.0.0.1 --port 8000
```

Expected output should include:

```text
Uvicorn running on http://127.0.0.1:8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected output:

```json
{"status":"ok","system":"huginn-muninn"}
```

Send a chat command:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hey Huginn, analyze these logs."}'
```

Expected output:

```json
{"status":"accepted","event_id":"..."}
```

Check events:

```bash
curl http://127.0.0.1:8000/events
```

Expected output:

```text
JSON list of event log entries
```

### Test Graph Intelligence API Endpoints

These endpoints are read-only. They only read the existing JSON graph files.

Like you are 10:

These commands ask Munnin questions about its map.

Graph summary:

```bash
curl http://127.0.0.1:8000/graph/summary
```

Expected response shape:

```json
{
  "entity_searched": "knowledge_graph",
  "summary": {
    "total_nodes": 43,
    "total_relationships": 42
  },
  "connected_entities": [],
  "weaknesses": [],
  "recommendations": [],
  "similar_incidents": [],
  "explanation": "..."
}
```

Related entities:

```bash
curl http://127.0.0.1:8000/graph/related/mitre:T1078
```

Expected response shape:

```json
{
  "entity_searched": "mitre:T1078",
  "normalized_entity": "mitre:T1078",
  "connected_entities": [],
  "weaknesses": [],
  "recommendations": [],
  "similar_incidents": [],
  "explanation": "..."
}
```

Connected weaknesses:

```bash
curl http://127.0.0.1:8000/graph/weaknesses/T1078
```

Expected response shape:

```json
{
  "entity_searched": "T1078",
  "normalized_entity": "mitre:T1078",
  "connected_entities": [],
  "weaknesses": [],
  "recommendations": [],
  "similar_incidents": [],
  "explanation": "..."
}
```

Recommendations for a technique:

```bash
curl http://127.0.0.1:8000/graph/recommendations/T1078
```

Expected response shape:

```json
{
  "entity_searched": "T1078",
  "normalized_entity": "mitre:T1078",
  "connected_entities": [],
  "weaknesses": [],
  "recommendations": [],
  "similar_incidents": [],
  "explanation": "..."
}
```

Similar incidents:

```bash
curl http://127.0.0.1:8000/graph/similar-incidents/f26fa03a-6c8e-44ca-b906-12c974dcbcbf
```

Expected response shape:

```json
{
  "entity_searched": "f26fa03a-6c8e-44ca-b906-12c974dcbcbf",
  "normalized_entity": "event:f26fa03a-6c8e-44ca-b906-12c974dcbcbf",
  "connected_entities": [],
  "weaknesses": [],
  "recommendations": [],
  "similar_incidents": [],
  "explanation": "..."
}
```

### Start the Web Frontend

Open a second terminal.

From the repository root:

```bash
cd apps/web
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
npm install
npm run dev
```

Expected output should include:

```text
Local: http://127.0.0.1:3000
```

Open:

```text
http://127.0.0.1:3000/
```

### Verify the Graph Intelligence Panel

The dashboard now has a simple Graph Intelligence panel.

Before opening the dashboard, make sure the API is running:

```bash
cd apps/api
.venv/bin/uvicorn huginn_muninn_api.main:app --reload --host 127.0.0.1 --port 8000
```

Then start the web app in another terminal:

```bash
cd apps/web
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
npm run dev
```

Open:

```text
http://127.0.0.1:3000/
```

Expected panel content:

- total graph nodes
- total graph relationships
- top connected entities
- related entities for `T1078`
- connected weaknesses for `T1078`
- defense recommendations for `T1078`
- similar incidents for the sample event

If the panel says Graph Intelligence is not available, check that the API is
running on:

```text
http://127.0.0.1:8000
```

You can also verify the API directly:

```bash
curl http://127.0.0.1:8000/graph/summary
curl http://127.0.0.1:8000/graph/recommendations/T1078
```

Like you are 10:

The dashboard now shows part of Munnin's map. It shows how many clue cards are
on the map, which cards are connected, which weak spots matter, and which fix-it
ideas Huginn should look at.

### Web Tooling Troubleshooting

Use Node 22 for the dashboard:

```bash
cd apps/web
export PATH="/opt/homebrew/opt/node@22/bin:$PATH"
node --version
```

Expected output should start with:

```text
v22.
```

Run checks:

```bash
npm run build
```

`npm run build` is the current stable web validation command. It compiles the
dashboard and runs Next.js type validation. `npm run lint`, direct ESLint, and
standalone TypeScript checks may still hang in this local environment, so do
not use them as the release gate until the tooling stack is revisited.

Like you are 10:

Node is the engine. npm installs the dashboard parts. Next builds the dashboard
and checks that the parts fit together before the browser opens it.

## Testing

### Recommended Test Command

Use this command for focused graph tests:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 apps/api/.venv/bin/python -m pytest \
  apps/api/tests/test_knowledge_graph.py \
  apps/api/tests/test_graph_intelligence.py \
  apps/api/tests/test_graph_api.py \
  -q
```

Expected output:

```text
.............                                                            [100%]
13 passed
```

### Ruff

Run:

```bash
apps/api/.venv/bin/ruff check core apps/api/tests
```

Expected output:

```text
All checks passed!
```

### Compile Check

Run:

```bash
apps/api/.venv/bin/python -m compileall core apps/api/tests
```

Expected output:

```text
Listing 'core'...
Listing 'apps/api/tests'...
```

No Python syntax errors should appear.

## Troubleshooting

### Pytest Hangs Before Showing Output

Symptom:

```text
pytest starts but prints nothing for a long time
```

Use the recommended command:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 apps/api/.venv/bin/python -m pytest \
  apps/api/tests/test_knowledge_graph.py \
  apps/api/tests/test_graph_intelligence.py \
  -q
```

Why:

Some local pytest plugins can hang during startup before the tests are even
collected. The graph tests do not need those plugins.

Like you are 10:

Pytest is trying to load extra tools before it starts. One extra tool can get
stuck. This command tells pytest, "Do not load the extra tools. Just run the
tests."

### Wrong Python Version

Check:

```bash
apps/api/.venv/bin/python --version
```

Recommended:

```text
Python 3.11.x
```

If needed, recreate the venv:

```bash
rm -rf apps/api/.venv
python3.11 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -e 'apps/api[dev]'
```

### Missing Knowledge Graph Report

If this file is missing:

```text
reports/knowledge-graph.json
```

Run:

```bash
apps/api/.venv/bin/python -c 'from core.graph_context_builder import GraphContextBuilder; GraphContextBuilder().build(persist=True)'
```

Then verify:

```bash
test -f reports/knowledge-graph.json && echo "knowledge graph exists"
```

Expected output:

```text
knowledge graph exists
```

### Missing Graph Intelligence Report

If this file is missing:

```text
reports/graph-intelligence-report.json
```

Run:

```bash
apps/api/.venv/bin/python -c 'from core.graph_intelligence import write_sample_report; write_sample_report()'
```

Then verify:

```bash
test -f reports/graph-intelligence-report.json && echo "graph intelligence report exists"
```

Expected output:

```text
graph intelligence report exists
```

## Quick Local Checklist

Run these commands:

```bash
apps/api/.venv/bin/python --version
apps/api/.venv/bin/python -c 'from core.graph_context_builder import GraphContextBuilder; GraphContextBuilder().build(persist=True)'
apps/api/.venv/bin/python -c 'from core.graph_intelligence import write_sample_report; write_sample_report()'
apps/api/.venv/bin/ruff check core apps/api/tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 apps/api/.venv/bin/python -m pytest apps/api/tests/test_knowledge_graph.py apps/api/tests/test_graph_intelligence.py -q
```

If those work, local graph intelligence is ready.
