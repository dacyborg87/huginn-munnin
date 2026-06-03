# Reports

Incident reports and completed lab writeups belong here.

Use [templates/incident-report-template.md](../templates/incident-report-template.md) for new reports.

Reports should be:

- timestamped
- evidence-driven
- mapped to MITRE ATT&CK
- clear about impact and response
- concise enough for Tier 1 handoff and Tier 2 review

Runtime integration files may be generated here:

- `soc-events.jsonl`: canonical event bus activity
- `detection-outcomes.jsonl`: analyst-reviewed detection outcomes
- `soc-health-report.json`: structured SOC metrics output
- `attack-chain-analysis.json`: reconstructed MITRE technique chains and missing transitions
- `coverage-matrix.json`: technique-level detection, correlation, and response coverage
- `prioritized-gaps.json`: ranked detection gap list
- `attack-success-probability.json`: estimated chain success probability and risk score
- `defense-priorities.json`: ranked defensive improvement candidates
- `defense-plan.json`: structured defensive action plan
- `defense-learning-insights.json`: recurring weakness and structural failure findings
- `defense-evolution-metrics.json`: latest defensive improvement snapshot
- `defense-evolution-history.jsonl`: historical defensive posture snapshots
- `security-architecture-weaknesses.json`: system-level architecture blind spots
- `attack-surface-model.json`: pre-auth, auth, and post-auth instrumentation model
- `defense-design-recommendations.json`: subsystem and architecture recommendations
- `defense-complexity-insights.json`: coverage versus complexity simplification findings

These files provide memory input for Huginn/Muninn reasoning and feedback analysis.
