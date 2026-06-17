# Phase 5C: Wazuh Ingestion API

Phase 5C adds a controlled runtime entry point for Wazuh alerts.

## Purpose

Huginn/Muninn already had a Wazuh file-to-intelligence pipeline. Phase 5C closes
the runtime input gap by allowing a running API server to accept Wazuh alert JSON
payloads and push them through the same intelligence path used by the existing
file pipeline.

## Endpoint Contract

```http
POST /ingest/wazuh
Content-Type: application/json
```

The endpoint accepts either:

- One Wazuh alert JSON object
- A list of Wazuh alert JSON objects

The endpoint returns a summary of what was received, parsed, added to the graph,
and converted into evidence.

## Example Request

```bash
curl -X POST http://localhost:8000/ingest/wazuh \
  -H "Content-Type: application/json" \
  -d '{
    "id": "1700000000.12345",
    "timestamp": "2026-06-17T12:00:00.000Z",
    "agent": {
      "name": "windows-endpoint-01"
    },
    "rule": {
      "id": "60122",
      "level": 10,
      "description": "Multiple Windows logon failures",
      "mitre": {
        "id": ["T1110", "T1078"]
      }
    }
  }'
```

## Example Response

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

## Runtime Flow

```text
Wazuh alert JSON
↓
POST /ingest/wazuh
↓
WazuhIngestApi
↓
parse_wazuh_alert()
↓
EventRecord
↓
ingest_event_records()
↓
Knowledge Graph event and MITRE relationships
↓
build_real_data_evidence()
↓
reports/real-data-pipeline-output.json
↓
Live Telemetry API refresh
↓
Dashboard update
```

## How This Closes The Runtime Input Gap

Before Phase 5C, Huginn/Muninn could process copied Wazuh alert files, but the
running API did not have a controlled ingestion endpoint for new Wazuh telemetry.

Phase 5C adds that missing runtime entry point while keeping the implementation
small:

- No database was added.
- No queue was added.
- No authentication was added yet.
- No dashboard changes were required.
- The existing live telemetry report format is reused.

## Known Limitations

- Authentication is not implemented yet.
- Batch ingestion is accepted as a list, but there is no queue or streaming
  worker.
- The endpoint writes the current live telemetry report artifact, so future
  versions should decide whether to append, merge, or archive prior telemetry.
- Malformed non-object records are skipped safely, but deeper semantic validation
  remains minimal.
- This phase only handles Wazuh alerts. GuardDuty, CloudTrail, and other cloud
  sources are not included yet.

## Next Phase Recommendation

The next recommended phase is authenticated live ingestion.

Recommended next steps:

- Add an API token or local-only allowlist for ingestion.
- Add source tagging for Wazuh manager identity.
- Add append/merge behavior for report history.
- Add dashboard visibility for last ingestion time and records skipped.
- Add a separate cloud detection parser after the Wazuh runtime path is stable.

## Explain Like I Am 10

Before this phase, Huginn could read a Wazuh alert file from disk. Now Huginn has
a safe front door where another system can hand it a Wazuh alert while the API is
running. Huginn turns that alert into graph data and evidence, then the dashboard
can refresh and show what changed.
