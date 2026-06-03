# Architecture

## Core Orchestrator

The orchestrator routes user intent through an adaptive intelligence graph:

- Huginn handles thought, planning, reasoning, research, security analysis, automation, and agent control.
- Muninn handles durable memory, profile context, project archives, knowledge graph entries, vector retrieval, and learning loops.
- The event bus accepts commands, queues events, dispatches subscribed handlers, and records every event to `system_logs` using an in-memory fallback until Postgres persistence is wired.
- The decision engine scores candidate states using user intent, task complexity, and relevant Muninn memory.
- The intelligence graph resolves the next state dynamically instead of enforcing a fixed `analysis -> planning -> execution` path.
- The outcome tracker records execution results and updates learned path weights so future decisions adapt to past success, partial completion, or failure.
- The reasoning pattern engine abstracts past executions into context patterns so Huginn can generalize from similar situations, not only repeat path-level weights.

## Intelligence Graph

Core graph primitives live in `apps/api/src/core/intelligence_graph.py`:

- `Node`: state id, state type, handler function, and possible transitions.
- `Transition`: condition function and target node.
- `Graph`: node registry, transition registration, and next-state resolution.

Current Huginn branches:

- `PLANNING`: structured reasoning and plan creation.
- `MEMORY_LOOKUP`: Muninn-first contextual retrieval.
- `TOOL_USE`: operational execution branch, including cybersecurity analysis.

## Closed-Loop Learning

Execution outcomes are captured in `apps/api/src/core/outcome_tracker.py`.

Each outcome records:

- execution event id
- initial state
- chosen path
- result: `success`, `failure`, or `partial`
- execution time
- error logs
- optional user feedback placeholder
- performance score

Successful paths receive a positive learned weight. Failed paths receive a negative learned weight. Outcome snapshots and updated weights are written into Muninn memory using `learning_weights` records, then reloaded before the decision engine evaluates future commands.

## Reasoning Patterns

Reasoning patterns live in `apps/api/src/core/reasoning_patterns.py` and are persisted to `apps/api/data/reasoning_patterns.json`.

Each request produces a context signature with:

- intent
- mock intent embedding
- memory relevance summary
- memory relevance score
- system state at decision time
- normalized request tokens

The pattern engine compares the current signature to historical patterns, returns nearest matches, and converts successful similar patterns into path-specific influence scores. The decision engine combines raw scores, learned weights, and pattern influence before graph resolution.

After every outcome, Huginn updates or creates a pattern containing:

- `pattern_id`
- `context_signature`
- `preferred_path_distribution`
- `success_rate`
- `conditions`

## Event Types

- `USER_COMMAND_RECEIVED`
- `CONTEXT_SIGNATURE_CREATED`
- `PATTERN_MATCH_LOOKUP`
- `AI_THINKING_STARTED`
- `AI_DECISION_MADE`
- `AI_PLAN_CREATED`
- `AI_TASK_EXECUTING`
- `AI_TASK_COMPLETED`
- `AI_OUTCOME_RECORDED`
- `AI_PATTERN_RECORDED`
- `MEMORY_WRITTEN`
- `AGENT_STATUS_UPDATED`

The `/chat` API does not return final AI output. It returns `{ "status": "accepted", "event_id": "..." }`, and graph progress is observable through `/events`. Each `AI_DECISION_MADE` event includes candidate states, selected state, confidence scores, reasoning, and memory context.

## Backend Modules

```text
huginn_muninn_api/
  main.py
  core/event_bus.py
  core/decision_engine.py
  core/intelligence_graph.py
  core/
    config.py
    orchestrator.py
  huginn/
    engine.py
    security.py
  muninn/
    memory.py
  schemas/
    chat.py
    memory.py
    security.py
```

## Safety Model

Cybersecurity features are assistive by default. The platform should support defensive analysis, reporting, IOC enrichment, and incident response workflows while requiring explicit authorization for active scanning or system automation.

## Phase Progression

1. Chat + memory.
2. Voice + dashboard.
3. Cybersecurity operations center.
4. Multi-agent ecosystem.
5. Autonomous workflow execution.
6. Personal AI operating system.
