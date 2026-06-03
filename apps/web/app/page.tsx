"use client";

import { motion } from "framer-motion";
import { Activity, BrainCircuit, Database, Mic, Radar, Send, ShieldCheck } from "lucide-react";
import { useState } from "react";

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

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
