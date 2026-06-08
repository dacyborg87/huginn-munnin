"use client";

import { motion } from "framer-motion";
import { Activity, BrainCircuit, Database, Mic, Radar, Send, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type ChatAcceptedResponse = {
  status: string;
  event_id: string;
};

type EventLogEntry = {
  id: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type DecisionPayload = {
  candidate_states?: string[];
  selected_state?: string;
  confidence_scores?: Record<string, number>;
  learned_weights?: Record<string, number>;
  pattern_influence?: Record<string, number>;
  matched_patterns?: Array<{
    pattern_id: string;
    similarity: number;
    success_rate: number;
    preferred_path_distribution: Record<string, number>;
  }>;
  reasoning?: string;
  current_state?: string;
};

type OutcomePayload = {
  selected_path?: string;
  result?: "success" | "failure" | "partial";
  performance_score?: number;
  execution_time?: number;
  updated_weights?: Record<string, number>;
};

type GraphEntity = {
  id: string;
  type: string;
  label: string;
  connection_count?: number;
};

type GraphSummaryResponse = {
  summary?: {
    total_nodes?: number;
    total_relationships?: number;
    top_connected_entities?: GraphEntity[];
  };
  connected_entities?: GraphEntity[];
  explanation?: string;
};

type GraphQueryResponse = {
  connected_entities?: GraphEntity[];
  weaknesses?: GraphEntity[];
  recommendations?: GraphEntity[];
  similar_incidents?: GraphEntity[];
  explanation?: string;
};

type GraphPanelState = {
  summary: GraphSummaryResponse | null;
  related: GraphQueryResponse | null;
  weaknesses: GraphQueryResponse | null;
  recommendations: GraphQueryResponse | null;
  similarIncidents: GraphQueryResponse | null;
  status: "loading" | "ready" | "error";
};

type EvidenceRecord = {
  evidence_id: string;
  title: string;
  summary: string;
  source_reference: string;
  related_entities: {
    events?: string[];
    mitre_techniques?: string[];
    architecture_weaknesses?: string[];
    defense_recommendations?: string[];
  };
  confidence: {
    level: string;
    score: number;
    explanation: string;
  };
};

type EvidenceSummaryResponse = {
  summary?: {
    total_records?: number;
    confidence_counts?: Record<string, number>;
  };
  evidence_records?: EvidenceRecord[];
  explanation?: string;
};

type EvidenceQueryResponse = {
  evidence_records?: EvidenceRecord[];
  match_count?: number;
  explanation?: string;
};

type EvidencePanelState = {
  summary: EvidenceSummaryResponse | null;
  finding: EvidenceQueryResponse | null;
  mitre: EvidenceQueryResponse | null;
  weakness: EvidenceQueryResponse | null;
  recommendation: EvidenceQueryResponse | null;
  gap: EvidenceQueryResponse | null;
  status: "loading" | "ready" | "error";
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const sampleTechniqueId = "T1078";
const sampleEventId = "f26fa03a-6c8e-44ca-b906-12c974dcbcbf";
const sampleWeaknessId = "15953a2c-3b98-4640-9401-1306f95162e3";
const sampleRecommendationId = "design.post_auth_telemetry_layer";

const systems = [
  { label: "Huginn", detail: "Thought Engine", icon: BrainCircuit, status: "online" },
  { label: "Muninn", detail: "Memory Engine", icon: Database, status: "online" },
  { label: "Voice", detail: "Hey Huginn", icon: Mic, status: "planned" },
  { label: "SOC", detail: "Wazuh + Suricata", icon: ShieldCheck, status: "scaffolded" },
];

export default function Home() {
  const [message, setMessage] = useState("Hey Huginn, analyze these logs.");
  const [acceptedCommand, setAcceptedCommand] = useState<ChatAcceptedResponse | null>(null);
  const [events, setEvents] = useState<EventLogEntry[]>([]);
  const [securityText, setSecurityText] = useState(
    "Wazuh alert: failed password followed by powershell -enc payload.",
  );
  const [securityResult, setSecurityResult] = useState<string>("No analysis submitted.");
  const [isLoading, setIsLoading] = useState(false);
  const [graphPanel, setGraphPanel] = useState<GraphPanelState>({
    summary: null,
    related: null,
    weaknesses: null,
    recommendations: null,
    similarIncidents: null,
    status: "loading",
  });
  const [evidencePanel, setEvidencePanel] = useState<EvidencePanelState>({
    summary: null,
    finding: null,
    mitre: null,
    weakness: null,
    recommendation: null,
    gap: null,
    status: "loading",
  });

  const latestDecision = events
    .slice()
    .reverse()
    .find((event) => event.event_type === "AI_DECISION_MADE")?.payload as
    | DecisionPayload
    | undefined;
  const outcomes = events
    .filter((event) => event.event_type === "AI_OUTCOME_RECORDED")
    .map((event) => event.payload as OutcomePayload);
  const latestOutcome = outcomes.at(-1);
  const latestWeights = latestOutcome?.updated_weights ?? latestDecision?.learned_weights;
  const patternInfluence = latestDecision?.pattern_influence;
  const branchStats = outcomes.reduce<Record<string, { total: number; success: number }>>(
    (stats, outcome) => {
      const path = outcome.selected_path ?? "UNKNOWN";
      stats[path] = stats[path] ?? { total: 0, success: 0 };
      stats[path].total += 1;
      if (outcome.result === "success") {
        stats[path].success += 1;
      }
      return stats;
    },
    {},
  );

  async function refreshEvents() {
    const result = await fetch(`${apiUrl}/events?limit=50`);
    setEvents(await result.json());
  }

  const refreshGraphIntelligence = useCallback(async () => {
    setGraphPanel((current) => ({ ...current, status: "loading" }));
    try {
      const [summary, related, weaknesses, recommendations, similarIncidents] =
        await Promise.all([
          fetch(`${apiUrl}/graph/summary`).then((response) => response.json()),
          fetch(`${apiUrl}/graph/related/mitre:${sampleTechniqueId}`).then((response) =>
            response.json(),
          ),
          fetch(`${apiUrl}/graph/weaknesses/${sampleTechniqueId}`).then((response) =>
            response.json(),
          ),
          fetch(`${apiUrl}/graph/recommendations/${sampleTechniqueId}`).then((response) =>
            response.json(),
          ),
          fetch(`${apiUrl}/graph/similar-incidents/${sampleEventId}`).then((response) =>
            response.json(),
          ),
        ]);
      setGraphPanel({
        summary,
        related,
        weaknesses,
        recommendations,
        similarIncidents,
        status: "ready",
      });
    } catch {
      setGraphPanel((current) => ({ ...current, status: "error" }));
    }
  }, []);

  useEffect(() => {
    void refreshGraphIntelligence();
  }, [refreshGraphIntelligence]);

  const refreshEvidence = useCallback(async () => {
    setEvidencePanel((current) => ({ ...current, status: "loading" }));
    try {
      const [summary, finding, mitre, weakness, recommendation, gap] = await Promise.all([
        fetch(`${apiUrl}/evidence/summary`).then((response) => response.json()),
        fetch(`${apiUrl}/evidence/finding/weakness:${sampleWeaknessId}`).then((response) =>
          response.json(),
        ),
        fetch(`${apiUrl}/evidence/mitre/${sampleTechniqueId}`).then((response) =>
          response.json(),
        ),
        fetch(`${apiUrl}/evidence/weakness/${sampleWeaknessId}`).then((response) =>
          response.json(),
        ),
        fetch(`${apiUrl}/evidence/recommendation/${sampleRecommendationId}`).then((response) =>
          response.json(),
        ),
        fetch(`${apiUrl}/evidence/finding/finding:does-not-exist`).then((response) =>
          response.json(),
        ),
      ]);
      setEvidencePanel({
        summary,
        finding,
        mitre,
        weakness,
        recommendation,
        gap,
        status: "ready",
      });
    } catch {
      setEvidencePanel((current) => ({ ...current, status: "error" }));
    }
  }, []);

  useEffect(() => {
    void refreshEvidence();
  }, [refreshEvidence]);

  async function sendChat() {
    setIsLoading(true);
    try {
      const result = await fetch(`${apiUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      setAcceptedCommand(await result.json());
      await refreshEvents();
      window.setTimeout(refreshEvents, 500);
    } finally {
      setIsLoading(false);
    }
  }

  async function analyzeSecurity() {
    const result = await fetch(`${apiUrl}/security/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: securityText, source: "dashboard" }),
    });
    const body = await result.json();
    setSecurityResult(`${body.severity.toUpperCase()}: ${body.summary}`);
  }

  return (
    <main className="min-h-screen bg-[#eef3f4]">
      <section className="border-b border-command-line bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div>
            <h1 className="text-xl font-semibold tracking-normal">HUGINN // MUNINN</h1>
            <p className="text-sm text-neutral-600">AI command center</p>
          </div>
          <div className="flex items-center gap-2 text-sm text-command-signal">
            <Radar size={18} />
            Operational
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-5 py-6 lg:grid-cols-[1.4fr_0.9fr]">
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-lg border border-command-line bg-white p-5 shadow-panel"
        >
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Conversation</h2>
              <p className="text-sm text-neutral-600">Commands enter the persistent event loop.</p>
            </div>
            <BrainCircuit className="text-command-signal" size={24} />
          </div>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            className="min-h-32 w-full resize-none rounded-md border border-command-line p-3 outline-none focus:border-command-signal"
          />
          <div className="mt-3 flex justify-end">
            <button
              onClick={sendChat}
              className="inline-flex items-center gap-2 rounded-md bg-command-ink px-4 py-2 text-sm font-medium text-white"
            >
              <Send size={16} />
              {isLoading ? "Sending" : "Send"}
            </button>
          </div>
          <div className="mt-5 rounded-md border border-command-line bg-command-panel p-4">
            <p className="text-sm font-medium text-neutral-700">Command State</p>
            <p className="mt-2 text-sm leading-6 text-neutral-800">
              {acceptedCommand
                ? `Accepted into event loop: ${acceptedCommand.event_id}`
                : "Awaiting command."}
            </p>
            {acceptedCommand && (
              <p className="mt-3 text-xs uppercase text-neutral-500">
                Status: {acceptedCommand.status}
              </p>
            )}
          </div>

          <div className="mt-5 rounded-md border border-command-line bg-white p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-neutral-700">Event Stream</p>
              <button
                onClick={refreshEvents}
                className="inline-flex items-center gap-2 rounded-md border border-command-line px-3 py-1.5 text-xs font-medium text-neutral-700"
              >
                <Activity size={14} />
                Refresh
              </button>
            </div>
            <div className="mt-3 grid gap-2">
              {events.length === 0 ? (
                <p className="text-sm text-neutral-600">No events observed yet.</p>
              ) : (
                events
                  .slice()
                  .reverse()
                  .map((event) => (
                    <div
                      key={event.id}
                      className="rounded-md border border-command-line bg-command-panel p-3"
                    >
                      <p className="text-xs font-semibold text-command-ink">{event.event_type}</p>
                      <p className="mt-1 truncate text-xs text-neutral-600">{event.id}</p>
                    </div>
                  ))
              )}
            </div>
          </div>
        </motion.div>

        <div className="grid gap-5">
          <div className="rounded-lg border border-command-line bg-white p-5 shadow-panel">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Decision Graph</h2>
              <Activity className="text-command-signal" size={22} />
            </div>
            {latestDecision?.confidence_scores ? (
              <div className="grid gap-3">
                <div className="rounded-md border border-command-line bg-command-panel p-3">
                  <p className="text-xs uppercase text-neutral-500">
                    {latestDecision.current_state ?? "THINKING"} routes to
                  </p>
                  <p className="mt-1 text-sm font-semibold text-command-ink">
                    {latestDecision.selected_state}
                  </p>
                  <p className="mt-2 text-sm leading-5 text-neutral-700">
                    {latestDecision.reasoning}
                  </p>
                  {latestWeights && latestDecision.selected_state && (
                    <p className="mt-2 text-xs text-neutral-600">
                      Weight influence:{" "}
                      {`${(latestWeights[latestDecision.selected_state] ?? 0).toFixed(2)}`}
                    </p>
                  )}
                  {patternInfluence && latestDecision.selected_state && (
                    <p className="mt-1 text-xs text-neutral-600">
                      Pattern influence:{" "}
                      {`${(patternInfluence[latestDecision.selected_state] ?? 0).toFixed(2)}`}
                    </p>
                  )}
                </div>
                {Object.entries(latestDecision.confidence_scores).map(([state, score]) => (
                  <div key={state}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium text-neutral-700">{state}</span>
                      <span className="text-neutral-500">{Math.round(score * 100)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-command-panel">
                      <div
                        className={`h-2 rounded-full ${
                          state === latestDecision.selected_state
                            ? "bg-command-signal"
                            : "bg-command-line"
                        }`}
                        style={{ width: `${Math.round(score * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
                <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-xs text-neutral-600">
                  <span className="rounded-md border border-command-line p-2 text-center">
                    THINKING
                  </span>
                  <span>routes</span>
                  <span className="rounded-md border border-command-line bg-command-panel p-2 text-center font-semibold text-command-ink">
                    {latestDecision.selected_state}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-sm text-neutral-600">No decisions observed yet.</p>
            )}
          </div>

          <div className="rounded-lg border border-command-line bg-white p-5 shadow-panel">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Reasoning Intelligence</h2>
              <BrainCircuit className="text-command-signal" size={22} />
            </div>
            {latestDecision?.matched_patterns?.length ? (
              <div className="grid gap-4">
                <div className="rounded-md border border-command-line bg-command-panel p-3">
                  <p className="text-xs font-semibold uppercase text-neutral-500">
                    Path Preference
                  </p>
                  <p className="mt-2 text-sm text-neutral-800">
                    Huginn combines learned weights with similar reasoning patterns before
                    selecting {latestDecision.selected_state}.
                  </p>
                </div>
                {latestDecision.matched_patterns.map((pattern) => (
                  <div key={pattern.pattern_id} className="rounded-md border border-command-line p-3">
                    <p className="truncate text-xs font-semibold text-command-ink">
                      {pattern.pattern_id}
                    </p>
                    <div className="mt-2 grid gap-2 text-xs">
                      <div className="flex justify-between">
                        <span>Similarity</span>
                        <span>{Math.round(pattern.similarity * 100)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Success Rate</span>
                        <span>{Math.round(pattern.success_rate * 100)}%</span>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-1">
                      {Object.entries(pattern.preferred_path_distribution).map(([path, share]) => (
                        <div key={path}>
                          <div className="mb-1 flex justify-between text-xs">
                            <span>{path}</span>
                            <span>{Math.round(share * 100)}%</span>
                          </div>
                          <div className="h-2 rounded-full bg-command-panel">
                            <div
                              className="h-2 rounded-full bg-command-signal"
                              style={{ width: `${Math.round(share * 100)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
                {patternInfluence && (
                  <div className="grid gap-2">
                    <p className="text-xs font-semibold uppercase text-neutral-500">
                      Pattern Influence
                    </p>
                    {Object.entries(patternInfluence).map(([path, value]) => (
                      <div key={path} className="flex items-center justify-between text-sm">
                        <span>{path}</span>
                        <span className={value >= 0 ? "text-command-signal" : "text-command-alert"}>
                          {value >= 0 ? "+" : ""}
                          {value.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-neutral-600">No matching reasoning patterns yet.</p>
            )}
          </div>

          <div className="rounded-lg border border-command-line bg-white p-5 shadow-panel">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Graph Intelligence</h2>
              <Database className="text-command-signal" size={22} />
            </div>
            {graphPanel.status === "error" ? (
              <p className="rounded-md border border-command-line bg-command-panel p-3 text-sm text-neutral-700">
                Graph Intelligence is not available. Start the API and refresh this panel.
              </p>
            ) : (
              <div className="grid gap-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-md border border-command-line bg-command-panel p-3">
                    <p className="text-xs uppercase text-neutral-500">Total Nodes</p>
                    <p className="mt-1 text-xl font-semibold text-command-ink">
                      {graphPanel.summary?.summary?.total_nodes ?? "Loading"}
                    </p>
                  </div>
                  <div className="rounded-md border border-command-line bg-command-panel p-3">
                    <p className="text-xs uppercase text-neutral-500">Relationships</p>
                    <p className="mt-1 text-xl font-semibold text-command-ink">
                      {graphPanel.summary?.summary?.total_relationships ?? "Loading"}
                    </p>
                  </div>
                </div>

                <GraphEntityList
                  title="Top Connected"
                  entities={
                    graphPanel.summary?.summary?.top_connected_entities ??
                    graphPanel.summary?.connected_entities ??
                    []
                  }
                />
                <GraphEntityList
                  title={`Related to ${sampleTechniqueId}`}
                  entities={graphPanel.related?.connected_entities ?? []}
                />
                <GraphEntityList
                  title="Connected Weaknesses"
                  entities={graphPanel.weaknesses?.weaknesses ?? []}
                />
                <GraphEntityList
                  title="Recommendations"
                  entities={graphPanel.recommendations?.recommendations ?? []}
                />
                <GraphEntityList
                  title="Similar Incidents"
                  entities={graphPanel.similarIncidents?.similar_incidents ?? []}
                />

                <button
                  onClick={refreshGraphIntelligence}
                  className="rounded-md border border-command-line px-3 py-2 text-sm font-medium text-neutral-700"
                >
                  Refresh Graph Intelligence
                </button>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-command-line bg-white p-5 shadow-panel">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Evidence</h2>
              <ShieldCheck className="text-command-signal" size={22} />
            </div>
            {evidencePanel.status === "error" ? (
              <p className="rounded-md border border-command-line bg-command-panel p-3 text-sm text-neutral-700">
                Evidence API is not available. Start the API and refresh this panel.
              </p>
            ) : (
              <div className="grid gap-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-md border border-command-line bg-command-panel p-3">
                    <p className="text-xs uppercase text-neutral-500">Evidence Records</p>
                    <p className="mt-1 text-xl font-semibold text-command-ink">
                      {evidencePanel.summary?.summary?.total_records ?? "Loading"}
                    </p>
                  </div>
                  <div className="rounded-md border border-command-line bg-command-panel p-3">
                    <p className="text-xs uppercase text-neutral-500">High Confidence</p>
                    <p className="mt-1 text-xl font-semibold text-command-ink">
                      {evidencePanel.summary?.summary?.confidence_counts?.high ?? "Loading"}
                    </p>
                  </div>
                </div>

                <ConfidenceLevels counts={evidencePanel.summary?.summary?.confidence_counts} />

                <EvidenceRecordCard
                  title="Sample Finding"
                  record={evidencePanel.finding?.evidence_records?.[0]}
                  explanation={evidencePanel.finding?.explanation}
                />

                <EvidenceFactList
                  title={`Related MITRE Techniques (${sampleTechniqueId})`}
                  values={uniqueEvidenceValues(
                    evidencePanel.mitre?.evidence_records,
                    "mitre_techniques",
                  )}
                />
                <EvidenceFactList
                  title="Related Weaknesses"
                  values={uniqueEvidenceValues(
                    evidencePanel.weakness?.evidence_records,
                    "architecture_weaknesses",
                  )}
                />
                <EvidenceFactList
                  title="Related Recommendations"
                  values={uniqueEvidenceValues(
                    evidencePanel.recommendation?.evidence_records,
                    "defense_recommendations",
                  )}
                />

                <div className="rounded-md border border-command-line bg-command-panel p-3">
                  <p className="text-xs font-semibold uppercase text-neutral-500">
                    Evidence Gaps
                  </p>
                  <p className="mt-2 text-sm text-neutral-700">
                    {evidencePanel.gap?.explanation ?? "Loading evidence gap example."}
                  </p>
                </div>

                <button
                  onClick={refreshEvidence}
                  className="rounded-md border border-command-line px-3 py-2 text-sm font-medium text-neutral-700"
                >
                  Refresh Evidence
                </button>
              </div>
            )}
          </div>

          <div className="rounded-lg border border-command-line bg-white p-5 shadow-panel">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Learning Loop</h2>
              <Database className="text-command-signal" size={22} />
            </div>
            {outcomes.length === 0 ? (
              <p className="text-sm text-neutral-600">No outcomes recorded yet.</p>
            ) : (
              <div className="grid gap-4">
                <div className="grid gap-2">
                  <p className="text-xs font-semibold uppercase text-neutral-500">
                    Outcome Timeline
                  </p>
                  {outcomes
                    .slice(-5)
                    .reverse()
                    .map((outcome, index) => (
                      <div
                        key={`${outcome.selected_path}-${index}`}
                        className="flex items-center justify-between rounded-md border border-command-line bg-command-panel p-3 text-sm"
                      >
                        <span className="font-medium text-command-ink">
                          {outcome.selected_path}
                        </span>
                        <span className="uppercase text-neutral-600">{outcome.result}</span>
                      </div>
                    ))}
                </div>

                <div className="grid gap-2">
                  <p className="text-xs font-semibold uppercase text-neutral-500">
                    Success Ratio
                  </p>
                  {Object.entries(branchStats).map(([path, stats]) => {
                    const ratio = stats.total ? stats.success / stats.total : 0;
                    return (
                      <div key={path}>
                        <div className="mb-1 flex justify-between text-xs">
                          <span>{path}</span>
                          <span>{Math.round(ratio * 100)}%</span>
                        </div>
                        <div className="h-2 rounded-full bg-command-panel">
                          <div
                            className="h-2 rounded-full bg-command-signal"
                            style={{ width: `${Math.round(ratio * 100)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>

                {latestWeights && (
                  <div className="grid gap-2">
                    <p className="text-xs font-semibold uppercase text-neutral-500">
                      Weight Shifts
                    </p>
                    {Object.entries(latestWeights).map(([path, weight]) => (
                      <div key={path} className="flex items-center justify-between text-sm">
                        <span>{path}</span>
                        <span
                          className={
                            weight >= 0 ? "text-command-signal" : "text-command-alert"
                          }
                        >
                          {weight >= 0 ? "+" : ""}
                          {weight.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="rounded-lg border border-command-line bg-white p-5 shadow-panel">
            <h2 className="text-lg font-semibold">System Layers</h2>
            <div className="mt-4 grid gap-3">
              {systems.map((system) => {
                const Icon = system.icon;
                return (
                  <div
                    key={system.label}
                    className="flex items-center justify-between rounded-md border border-command-line p-3"
                  >
                    <div className="flex items-center gap-3">
                      <Icon size={20} className="text-command-signal" />
                      <div>
                        <p className="text-sm font-medium">{system.label}</p>
                        <p className="text-xs text-neutral-600">{system.detail}</p>
                      </div>
                    </div>
                    <span className="text-xs uppercase text-neutral-500">{system.status}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-lg border border-command-line bg-white p-5 shadow-panel">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Security Analysis</h2>
              <ShieldCheck className="text-command-alert" size={22} />
            </div>
            <textarea
              value={securityText}
              onChange={(event) => setSecurityText(event.target.value)}
              className="min-h-24 w-full resize-none rounded-md border border-command-line p-3 text-sm outline-none focus:border-command-signal"
            />
            <button
              onClick={analyzeSecurity}
              className="mt-3 rounded-md bg-command-signal px-4 py-2 text-sm font-medium text-white"
            >
              Analyze
            </button>
            <p className="mt-3 rounded-md bg-command-panel p-3 text-sm text-neutral-800">
              {securityResult}
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}

function ConfidenceLevels({ counts }: { counts?: Record<string, number> }) {
  const levels = ["high", "medium", "low"];
  return (
    <div className="grid gap-2">
      <p className="text-xs font-semibold uppercase text-neutral-500">Confidence Levels</p>
      <div className="grid grid-cols-3 gap-2">
        {levels.map((level) => (
          <div key={level} className="rounded-md border border-command-line p-3">
            <p className="text-xs uppercase text-neutral-500">{level}</p>
            <p className="mt-1 text-sm font-semibold text-command-ink">
              {counts?.[level] ?? 0}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidenceRecordCard({
  title,
  record,
  explanation,
}: {
  title: string;
  record?: EvidenceRecord;
  explanation?: string;
}) {
  return (
    <div className="rounded-md border border-command-line p-3">
      <p className="text-xs font-semibold uppercase text-neutral-500">{title}</p>
      {record ? (
        <div className="mt-2 grid gap-2">
          <div>
            <p className="text-sm font-medium text-command-ink">{record.title}</p>
            <p className="mt-1 text-xs text-neutral-600">{record.evidence_id}</p>
          </div>
          <p className="text-sm leading-5 text-neutral-700">{record.summary}</p>
          <div className="grid gap-1 text-xs text-neutral-600">
            <p>Source: {record.source_reference}</p>
            <p>
              Confidence: {record.confidence.level} ({Math.round(record.confidence.score * 100)}%)
            </p>
            <p>{record.confidence.explanation}</p>
          </div>
          {explanation && <p className="text-xs text-neutral-600">{explanation}</p>}
        </div>
      ) : (
        <p className="mt-2 text-sm text-neutral-600">No evidence record loaded yet.</p>
      )}
    </div>
  );
}

function EvidenceFactList({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="grid gap-2">
      <p className="text-xs font-semibold uppercase text-neutral-500">{title}</p>
      {values.length === 0 ? (
        <p className="rounded-md border border-command-line bg-command-panel p-3 text-sm text-neutral-600">
          No evidence facts loaded yet.
        </p>
      ) : (
        values.slice(0, 5).map((value) => (
          <p
            key={value}
            className="truncate rounded-md border border-command-line bg-command-panel p-3 text-sm text-neutral-700"
          >
            {value}
          </p>
        ))
      )}
    </div>
  );
}

function uniqueEvidenceValues(
  records: EvidenceRecord[] | undefined,
  key: keyof EvidenceRecord["related_entities"],
) {
  const values = new Set<string>();
  records?.forEach((record) => {
    record.related_entities[key]?.forEach((value) => values.add(value));
  });
  return Array.from(values).sort();
}

function GraphEntityList({ title, entities }: { title: string; entities: GraphEntity[] }) {
  return (
    <div className="grid gap-2">
      <p className="text-xs font-semibold uppercase text-neutral-500">{title}</p>
      {entities.length === 0 ? (
        <p className="rounded-md border border-command-line bg-command-panel p-3 text-sm text-neutral-600">
          No graph data loaded yet.
        </p>
      ) : (
        entities.slice(0, 4).map((entity) => (
          <div key={entity.id} className="rounded-md border border-command-line p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-command-ink">{entity.label}</p>
                <p className="mt-1 truncate text-xs text-neutral-600">{entity.id}</p>
              </div>
              <span className="shrink-0 text-xs uppercase text-neutral-500">{entity.type}</span>
            </div>
            {typeof entity.connection_count === "number" && (
              <p className="mt-2 text-xs text-neutral-600">
                Connections: {entity.connection_count}
              </p>
            )}
          </div>
        ))
      )}
    </div>
  );
}
