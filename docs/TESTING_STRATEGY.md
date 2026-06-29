# Huginn/Muninn Testing Strategy

This document explains the stable way to test Huginn/Muninn locally without
tripping over known pytest, FastAPI, and local Node tooling issues.

## Current Testing Position

Huginn/Muninn has several layers that can be tested independently:

- Core graph and evidence logic
- Wazuh parsing and file-to-intelligence pipeline logic
- Live telemetry report summarization
- FastAPI endpoint wrappers
- Web dashboard rendering and build checks

The full backend suite is stable and currently completes with 127 passing
tests. Focused tests remain useful while developing a specific module, but no
test-file exclusions are required for the complete run.

## Historical Pytest Issues

Earlier local pytest runs sometimes hung during collection or produced
inconsistent graph results before project test code executed.

Observed causes:

- Pytest autoloading the `anyio` plugin.
- Test files importing `fastapi.testclient.TestClient`.
- FastAPI/TestClient pulling in `httpx`, `idna`, Starlette, and Pydantic during
  collection.
- Running tests from a directory where repository-root report paths are not
  resolved correctly.
- A stale `.venv` containing corrupted paths from an earlier environment.

The inconsistent behavior was traced to stale virtual-environment path
corruption. Recreating or correcting the environment resolved the issue. The
full suite now passes without ignored test files, and the prior graph state
isolation issue no longer reproduces.

## Why AnyIO Is Disabled

The API pytest configuration disables the AnyIO pytest plugin:

```toml
[tool.pytest.ini_options]
pythonpath = ["src"]
addopts = ["-p", "no:anyio"]
```

Reason:

Huginn/Muninn does not currently require AnyIO pytest markers for the focused
test suite, and the plugin has caused collection hangs in this local
environment. Disabling it keeps test discovery predictable.

## Why Some Tests Avoid FastAPI/TestClient

Some tests intentionally call helper classes directly instead of using
`fastapi.testclient.TestClient`.

Reason:

`TestClient` imports FastAPI, Starlette, HTTPX, and related dependencies during
test collection. In this local environment that import path has occasionally
hung before tests run.

Preferred approach:

- Test core behavior directly through classes such as `LiveTelemetryApi`,
  `GraphIntelligence`, and evidence query helpers.
- Keep endpoint-specific tests small.
- Use source-level route checks only when the goal is to confirm a route is
  wired and the TestClient stack is unstable.

## Correct PYTHONPATH Usage

When running API tests from `apps/api`, use the API source directory:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest tests/test_live_telemetry_api.py -q
```

Do not rely on plain `python` unless it is known to point to the project
environment. On this machine, `python` may not exist on PATH. Prefer:

```bash
apps/api/.venv/bin/python
```

or, from inside `apps/api`:

```bash
.venv/bin/python
```

## Correct Repository Root Handling

Several core modules read artifacts from repository-level folders such as:

- `reports/`
- `core/patterns/`

Tests must pass the repository root explicitly when building graphs or reading
report-backed data.

Correct pattern:

```python
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
graph = GraphContextBuilder(REPOSITORY_ROOT).build(persist=False)
```

Avoid this in tests:

```python
GraphContextBuilder().build(persist=False)
```

That version depends on the current working directory and may look under
`apps/api/reports/` instead of the repository root.

## Stable Focused Test Commands

Run live telemetry tests:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest tests/test_live_telemetry_api.py -q
```

Run graph tests:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_graph_intelligence.py \
  tests/test_knowledge_graph.py \
  -q
```

Run evidence tests:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_evidence_schema.py \
  tests/test_evidence_builder.py \
  tests/test_evidence_query.py \
  -q
```

Run Wazuh pipeline tests:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_wazuh_parser.py \
  tests/test_graph_ingest.py \
  tests/test_real_data_evidence.py \
  tests/test_wazuh_file_reader.py \
  tests/test_wazuh_pipeline.py \
  -q
```

Run a broad focused backend set without claiming full regression:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -m pytest tests/ -p no:anyio -x --tb=short
```

If this fails, inspect the first failure and determine whether it touches the
current change.

## Single Command Stable Test Run

Activate the API virtual environment, then use this command for the complete
known-good backend test run:

```bash
cd apps/api
PYTHONPATH=src python -m pytest tests/ -p no:anyio -v
```

Current result:

```text
127 passed
```

No `--ignore` exclusions are required. The stable command covers:

- Knowledge Graph
- Graph Intelligence
- Evidence schema, builder, and query
- Wazuh parser
- Graph ingest
- Real data evidence
- Wazuh file reader
- Wazuh file-to-intelligence pipeline
- Wazuh ingestion API
- Live telemetry API
- Intelligence context builder

## Graph Test Fixture Rules

The earlier graph state isolation inconsistency is resolved and does not
reproduce in the full suite. Its apparent behavior came from the corrupted
paths in a stale `.venv`, not from shared production graph state. Explicit
repository roots remain the preferred fixture pattern because they make test
inputs deterministic.

Graph tests should:

- Use `REPOSITORY_ROOT` explicitly.
- Avoid relying on the shell's current working directory.
- Build graph fixtures from known report data.
- Verify the graph has nodes and relationships before asserting query results.

Graph tests should not:

- Regenerate production reports unless that is the purpose of the test.
- Depend on dashboard or API startup.
- Assume `reports/` exists under `apps/api`.

## Live Telemetry Test Rules

Live telemetry tests should:

- Test `LiveTelemetryApi` directly.
- Use temporary report files for reload/cache behavior.
- Use a deterministic clock when checking timestamp changes.
- Verify stale cache behavior when a report is malformed or missing.
- Verify route wiring without requiring `TestClient` if FastAPI imports are
  unstable.

Live telemetry tests should not:

- Start the dashboard.
- Modify the Wazuh pipeline.
- Modify the report format.
- Start background polling during class construction.

Polling should start only through:

```python
await live_telemetry_api.start_polling()
```

and should stop cleanly through:

```python
await live_telemetry_api.stop_polling()
```

## API Test Caveats

API endpoint tests that import `fastapi.testclient.TestClient` now run as part
of the complete 127-test suite without exclusions.

Known files that import FastAPI/TestClient:

- `apps/api/tests/test_api.py`
- `apps/api/tests/test_graph_api.py`
- `apps/api/tests/test_evidence_api.py`

If collection problems return after an environment change:

1. Confirm the active interpreter belongs to `apps/api/.venv`.
2. Check the virtual environment for stale absolute paths.
3. Recreate the virtual environment if its paths reference an old location.
4. Use direct import checks:

```bash
cd apps/api
PYTHONPATH=src .venv/bin/python -c "from huginn_muninn_api.core.live_telemetry_api import LiveTelemetryApi; print('live telemetry import ok')"
```

5. Do not assume a core logic regression until the environment is ruled out.

## Web Build Caveats With Node 22

The web dashboard has had local build issues tied to the Homebrew Node
environment, including missing shared libraries such as `libsimdjson.27.dylib`.

Recommended approach:

- Use Node 22 for dashboard work.
- Verify `node --version` and `npm --version` before running web checks.
- Treat Node/Homebrew linkage failures as local toolchain issues, not dashboard
  source failures.

Useful checks:

```bash
cd apps/web
node --version
npm --version
npm run build
```

Do not claim a web build passed unless `npm run build` completes successfully.

## Commit Readiness Standard

Before committing a focused backend change, capture:

- Ruff result
- Python compile result
- Focused tests for the changed module
- Any known unrelated failures

Example:

```bash
cd apps/api
.venv/bin/python -m ruff check tests/test_live_telemetry_api.py
.venv/bin/python -m py_compile tests/test_live_telemetry_api.py
PYTHONPATH=src .venv/bin/python -m pytest tests/test_live_telemetry_api.py -q
```

If full regression is not run or does not pass, state that clearly.

## Simple Explanation

Think of the project like a big machine with many rooms. Testing every room at
once can get stuck because some doors are heavy. For now, test the room you are
working in first. If that room works, check nearby rooms. Only say the whole
building works when every room has actually been checked.
