# Repository Tree

Private repository layout:

```text
.
├── .env.example
├── .gitignore
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── docker-compose.yml
├── core
│   ├── README.md
│   ├── attack_chain_analyzer.py
│   ├── attack_surface_model.py
│   ├── attack_success_model.py
│   ├── context_builder.py
│   ├── coverage_matrix.py
│   ├── defense_complexity_engine.py
│   ├── defense_decision_engine.py
│   ├── defense_design_generator.py
│   ├── defense_evolution_tracker.py
│   ├── defense_learning_engine.py
│   ├── defense_prioritizer.py
│   ├── detection_response_map.py
│   ├── event_bus.py
│   ├── event_schema.py
│   ├── feedback_loop.py
│   ├── gap_analysis.py
│   ├── gap_prioritizer.py
│   ├── metrics_engine.py
│   ├── security_architecture_analyzer.py
│   ├── strategic_memory.py
│   └── patterns
│       └── README.md
├── labs
│   ├── README.md
│   └── 001-windows-auth-bruteforce
│       └── README.md
├── detection-engine
│   ├── README.md
│   ├── auditd
│   │   └── README.md
│   ├── suricata
│   │   └── rules
│   │       └── 001-smb-probe.rules
│   ├── sysmon
│   │   └── README.md
│   └── wazuh
│       └── rules
│           └── 001-windows-auth-bruteforce.xml
├── playbooks
│   ├── account-lockout.md
│   ├── network-containment.md
│   ├── README.md
│   └── windows-bruteforce-triage.md
├── reports
│   └── README.md
├── evidence
│   └── README.md
├── templates
│   ├── detection-rule-template.md
│   ├── incident-report-template.md
│   └── lab-readme-template.md
├── scripts
│   └── validate_wazuh_rules.py
├── apps
│   ├── api
│   │   ├── pyproject.toml
│   │   ├── src
│   │   │   ├── core
│   │   │   │   ├── decision_engine.py
│   │   │   │   ├── event_bus.py
│   │   │   │   ├── intelligence_graph.py
│   │   │   │   ├── outcome_tracker.py
│   │   │   │   └── reasoning_patterns.py
│   │   │   └── huginn_muninn_api
│   │   │       ├── main.py
│   │   │       ├── core
│   │   │       │   ├── config.py
│   │   │       │   └── orchestrator.py
│   │   │       ├── huginn
│   │   │       │   ├── engine.py
│   │   │       │   └── security.py
│   │   │       ├── muninn
│   │   │       │   └── memory.py
│   │   │       └── schemas
│   │   │           ├── chat.py
│   │   │           ├── events.py
│   │   │           ├── memory.py
│   │   │           └── security.py
│   │   └── tests
│   │       └── test_api.py
│   └── web
│       ├── app
│       │   ├── globals.css
│       │   ├── layout.tsx
│       │   └── page.tsx
│       ├── next.config.ts
│       ├── package-lock.json
│       ├── package.json
│       ├── postcss.config.mjs
│       ├── tailwind.config.ts
│       └── tsconfig.json
└── docs
    ├── architecture.md
    ├── event-flow.md
    ├── github-private-repo-checklist.md
    ├── repository-tree.md
    └── screenshots
        ├── dashboard.png
        ├── decision-graph.png
        ├── learning-loop.png
        └── reasoning-patterns.png
```

Excluded from Git:

- Python virtual environments
- Node dependencies
- Next.js build output
- Python caches and test caches
- Runtime reasoning-pattern JSON
- `.env` files and local configuration
- unsanitized evidence artifacts
