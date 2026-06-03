# Core Architecture

This directory documents the SOC platform core. The runnable Huginn/Muninn application currently lives under `apps/`:

- `apps/api`: FastAPI event bus, intelligence graph, learning loop, and reasoning pattern engine.
- `apps/web`: Next.js dashboard for events, decisions, outcomes, and reasoning visibility.

## Huginn

Huginn is the intelligence layer. It handles:

- event orchestration
- context signature creation
- decision routing
- reasoning graph selection
- outcome tracking
- pattern abstraction

## Muninn

Muninn is the memory layer. It handles:

- execution history
- outcome memory
- reasoning patterns
- recurrence tracking
- contextual retrieval for future decisions

## SOC Workflow

```text
attack simulation
  -> endpoint and network telemetry
  -> Wazuh and Suricata detections
  -> canonical SOC event bus
  -> Huginn event analysis and playbook routing
  -> Muninn pattern storage
  -> analyst playbook
  -> incident report
```

## SOC Integration Modules

- `event_schema.py`: canonical SOC event format for detections, labs, playbooks, reports, and memory feedback.
- `event_bus.py`: in-memory event bus for ingesting detection and lab events, then emitting structured SOC events.
- `detection_response_map.py`: detection-to-playbook routing without modifying sensor rules.
- `feedback_loop.py`: outcome logging to `reports/` and pattern suggestions to `core/patterns/`.
- `context_builder.py`: aggregated reasoning context from detections, labs, reports, and feedback history.
- `metrics_engine.py`: SOC health reporting from event bus history and outcome memory.
- `gap_analysis.py`: missed detection and weak coverage findings written to pattern memory.
- `attack_chain_analyzer.py`: MITRE technique sequence reconstruction and missing transition analysis.
- `coverage_matrix.py`: technique-level detection, correlation, and response coverage matrix.
- `gap_prioritizer.py`: ranked detection gap backlog based on chain severity and exposure risk.
- `attack_success_model.py`: attack-chain success probability and risk score estimates.
- `defense_prioritizer.py`: ranked defensive improvements by risk reduction and implementation efficiency.
- `defense_decision_engine.py`: structured defensive action plan for analyst-approved improvements.
- `defense_learning_engine.py`: recurring weakness and structural failure insight extraction.
- `defense_evolution_tracker.py`: coverage, risk, and gap-closure trend tracking.
- `strategic_memory.py`: long-term memory for repeated attack and failure combinations.
- `security_architecture_analyzer.py`: architecture-level blind spot analysis across chains, gaps, and memory.
- `attack_surface_model.py`: pre-auth, auth, and post-auth instrumentation exposure model.
- `defense_design_generator.py`: subsystem and architecture recommendation generation.
- `defense_complexity_engine.py`: complexity versus coverage and simplification analysis.
- `patterns/`: logged-only memory feedback for future Huginn/Muninn reasoning.

## Development Entry Points

- API: `apps/api/src/huginn_muninn_api/main.py`
- Orchestrator: `apps/api/src/huginn_muninn_api/core/orchestrator.py`
- Event bus: `apps/api/src/core/event_bus.py`
- Intelligence graph: `apps/api/src/core/intelligence_graph.py`
- Decision engine: `apps/api/src/core/decision_engine.py`
- Outcome tracker: `apps/api/src/core/outcome_tracker.py`
- Reasoning patterns: `apps/api/src/core/reasoning_patterns.py`
