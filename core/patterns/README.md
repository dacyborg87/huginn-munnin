# Pattern Feedback Memory

This directory stores logged-only intelligence feedback from detection outcomes.

Current policy:

- Store analyst-reviewed outcome patterns.
- Store detection tuning suggestions.
- Do not modify Wazuh, Suricata, Sysmon, or auditd content automatically.
- Promote suggestions to detection changes only after manual review.

Runtime feedback may create `suggestions.jsonl`.

Gap analysis may create `gap-findings.jsonl` with missed lab detections, weak coverage areas, and outcome quality concerns. These findings are backlog inputs only.

Attack-chain prioritization may create `prioritized-gaps.jsonl`. These records rank gaps by chain severity, exploitability after progression, and exposure risk.

The defensive learning loop may create:

- `defense-learning-insights.jsonl`: recurring weakness and structural failure insights.
- `strategic-memory.json`: long-term defensive intelligence patterns.

These artifacts are recommendation-only memory inputs.
