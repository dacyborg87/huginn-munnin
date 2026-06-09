# Next Session Start Here

## Purpose

This document is the restart guide for the next Huginn/Muninn work session.

Tonight validated that real Wazuh telemetry exists in the lab and that the Huginn/Muninn real-data pipeline is not the blocker. The current issue is a Windows telemetry collection gap for specific Security Event IDs.

## Current Platform Status

Confirmed operational:

- Knowledge Graph
- Graph Intelligence
- Evidence Layer
- Wazuh Parser
- Graph Ingest
- Real Data Evidence
- Wazuh File Reader
- Wazuh File-to-Intelligence Pipeline

Validation status:

```text
68 focused tests passing
```

## What Was Validated Tonight

Confirmed:

- Wazuh is running.
- The Windows agent is connected.
- Wazuh `alerts.json` exists.
- `alerts.json` was copied to a local test folder.
- The copied file contains real Wazuh alerts.
- Windows Security channel events are flowing.
- Event ID `4726` exists locally on Windows.
- Event ID `4726` is not reaching Wazuh alerts or archives.
- This is a telemetry collection gap, not a Huginn pipeline failure.

## Commands Used

Likely Wazuh alert file path:

```bash
/var/ossec/logs/alerts/alerts.json
```

Check whether Wazuh alerts exist:

```bash
sudo ls -lah /var/ossec/logs/alerts/alerts.json
```

Copy the Wazuh alerts file to a safe local test location:

```bash
mkdir -p ~/huginn-test
sudo cp /var/ossec/logs/alerts/alerts.json ~/huginn-test/alerts.json
sudo chown "$USER" ~/huginn-test/alerts.json
chmod 600 ~/huginn-test/alerts.json
```

Confirm the copied file exists:

```bash
ls -lah ~/huginn-test/alerts.json
```

Inspect a small sample safely:

```bash
head -n 5 ~/huginn-test/alerts.json
```

Search for Windows account-management events in the copied alert file:

```bash
grep '"id":"4720"' ~/huginn-test/alerts.json
grep '"id":"4726"' ~/huginn-test/alerts.json
```

Check whether Windows Security Event ID `4726` exists locally on Windows:

```powershell
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4726} -MaxEvents 5
```

Check whether Windows Security Event ID `4720` exists locally on Windows:

```powershell
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4720} -MaxEvents 5
```

## Files Copied

Copied from Wazuh:

```text
/var/ossec/logs/alerts/alerts.json
```

Copied to local test folder:

```text
~/huginn-test/alerts.json
```

Important:

Do not commit `~/huginn-test/alerts.json`.

That file may contain real IP addresses, hostnames, usernames, rule details, and private lab telemetry.

## Event ID 4720 / 4726 Issue

Relevant Windows Security Event IDs:

```text
4720 = A user account was created
4726 = A user account was deleted
```

What was discovered:

- Event `4726` exists locally on the Windows endpoint.
- Event `4726` does not appear in Wazuh `alerts.json`.
- Event `4726` does not appear in Wazuh archives.
- Security channel events are flowing in general.

Interpretation:

This is not a Huginn/Muninn parsing failure.

This is a telemetry collection or Wazuh configuration gap. The Windows endpoint is producing the event, but Wazuh is not collecting, archiving, or alerting on it.

## Why This Matters

Huginn/Muninn can only reason over telemetry it receives.

If Windows generates an important event but Wazuh does not collect it, then:

- the Wazuh parser has no record to parse
- graph ingest has no event to add
- evidence generation has no source fact
- the dashboard cannot display it
- the system may incorrectly appear blind to account lifecycle activity

For a SOC workflow, this is important because account creation and deletion events are useful for:

- insider threat investigations
- account misuse analysis
- privilege abuse detection
- persistence investigation
- post-incident timeline reconstruction

## What Not To Do Next

Do not immediately:

- rewrite the Huginn/Muninn parser
- modify graph ingest
- modify evidence logic
- build a Prediction Engine
- build Autonomous Investigation
- redesign the dashboard
- commit raw Wazuh alert files
- publish screenshots with real alert data
- assume Huginn/Muninn failed because Event `4726` was missing

The next step should not be more core intelligence logic.

The next step should make live telemetry visibility obvious in the dashboard.

## Recommended Next Phase

Recommended next phase:

```text
Live Telemetry Intelligence Dashboard
```

Why this is the right next phase:

- Real Wazuh telemetry has been confirmed.
- The pipeline can process Wazuh files.
- The current weakness is visibility into what telemetry is actually arriving.
- A dashboard will make collection gaps easy to see.
- It avoids overbuilding AI features before telemetry quality is clear.

## Next Dashboard Widgets

Build the smallest dashboard panel that reads existing pipeline output and shows:

- Recent Events
- Severity Breakdown
- Top Rules
- Top Agents
- Evidence Generated
- Evidence Gaps

The goal is not a full SOC dashboard yet.

The goal is to answer:

```text
What is Wazuh sending to Huginn/Muninn?
What is missing?
What evidence did Huginn create?
Where are the gaps?
```

## Suggested Next Implementation Scope

Smallest useful implementation:

1. Use existing Wazuh pipeline output.
2. Do not add live file watching yet.
3. Do not add database storage.
4. Do not modify Wazuh rules.
5. Add a read-only API endpoint or dashboard helper only if needed.
6. Display summary cards from `reports/real-data-pipeline-output.json`.

Possible files:

```text
apps/api/src/huginn_muninn_api/core/live_telemetry_api.py
apps/api/tests/test_live_telemetry_api.py
apps/web/app/page.tsx
docs/LIVE_TELEMETRY_DASHBOARD.md
```

Only create these if the next session explicitly asks for implementation.

## 10-Year-Old Explanation

Wazuh is like a security notebook.

Tonight we proved the notebook exists and has real notes in it.

We also proved Huginn can read Wazuh notes.

But one important Windows note, Event `4726`, is written on the Windows computer and is not showing up in the Wazuh notebook.

That means Huginn is not broken.

It means the note is not being delivered to Huginn yet.

Next, we should build a simple screen that shows which notes Huginn is getting and which ones are missing.

## SOC Analyst Explanation

Tonight validated the real telemetry path up to Wazuh alert file access.

The Wazuh manager is running, the Windows agent is connected, and `alerts.json` contains real Wazuh alerts. A copy was created at `~/huginn-test/alerts.json` for safe local testing.

The key finding is that Windows Security Event ID `4726` exists locally on the endpoint but is not present in Wazuh alerts or archives. Since other Security channel events are flowing, this points to a telemetry collection, archival, or rule coverage issue rather than a Huginn/Muninn parser or pipeline problem.

The next high-value move is a Live Telemetry Intelligence Dashboard that makes recent events, rule distribution, agent coverage, severity, generated evidence, and evidence gaps visible.

## Hiring Manager Explanation

This session moved the platform closer to real SOC utility.

The project validated that Wazuh is producing real alert data and that Huginn/Muninn has an operational file-to-intelligence pipeline ready to process it. The team also identified an important telemetry gap: a Windows account deletion event exists on the endpoint but is not reaching Wazuh outputs.

That distinction matters. It shows the platform is not just processing data blindly; it is being used to identify visibility gaps in the security telemetry pipeline.

The recommended next milestone is a Live Telemetry Intelligence Dashboard. This would show what telemetry is arriving, what evidence is being generated, and where collection gaps exist.

## Exact Next Codex Prompt

Use this prompt at the start of the next session:

```text
Implement the Live Telemetry Intelligence Dashboard MVP.

Goal:
Make real Wazuh pipeline output visible in the Huginn/Muninn dashboard.

Use existing:
- reports/real-data-pipeline-output.json
- core/ingest/wazuh_pipeline.py
- existing dashboard in apps/web/app/page.tsx

Requirements:
1. Show Recent Events.
2. Show Severity Breakdown.
3. Show Top Rules.
4. Show Top Agents.
5. Show Evidence Generated.
6. Show Evidence Gaps.
7. Use existing JSON output only.
8. Keep it read-only.
9. Do not add live file watching.
10. Do not modify Wazuh rules.
11. Do not commit raw Wazuh alert files.

If API support is needed, add the smallest read-only API endpoint that returns a telemetry summary from existing report JSON.

Validation:
- Run focused API tests if API code changes.
- Start the dashboard if possible.
- Confirm the dashboard renders the telemetry panel.

Explain everything like I am 10 years old.
```
