# Phase 5B: Interactive Intelligence Dashboard

Phase 5B adds an interactive event intelligence detail panel to the Huginn/Muninn
web dashboard.

## Purpose

The dashboard now lets an analyst click a recent security event or top rule ID
and inspect the connected intelligence context without leaving the main
telemetry view.

## Implemented Capability

- Recent Security Events rows are clickable.
- Top Rule IDs rows are clickable.
- Selecting an event or rule opens an intelligence detail panel.
- The panel displays:
  - Event summary
  - MITRE technique context
  - Evidence records
  - Evidence gaps
  - Plain-English explanation generated from available data
- Field-level fetch failures are shown in the affected section only.
- Empty states are shown for unmapped techniques, missing evidence, and missing
  gaps.

## API Usage

Phase 5B uses existing read-only API endpoints only:

- `GET /dashboard/events`
- `GET /graph/related/{entity_id}`
- `GET /graph/recommendations/{technique_id}`
- `GET /evidence/mitre/{technique_id}`
- `GET /evidence/summary`

No new API endpoints were added.

## Validation Status

Phase 5B frontend validation completed successfully.

- TypeScript validation passed.
- Production Next.js build passed.
- Interactive Intelligence Dashboard successfully builds.
- No new npm dependencies were added.

Validated environment:

```text
Node: v22.22.3
```

## Build Result

The production dashboard build completed successfully with `next build`.

This confirms the Phase 5B dashboard implementation is compatible with the
current Next.js application and TypeScript configuration.

## Scope Control

Phase 5B did not add:

- New npm packages
- Graph visualization libraries
- Authentication
- Persistence
- New backend routes
- Wazuh pipeline changes
- Evidence layer schema changes

## Explain Like I Am 10

Before Phase 5B, the dashboard showed lists of security events. Now you can
click one of those events and Huginn opens a detail box that explains what it
knows about that event, what evidence supports it, and whether anything is
missing.
