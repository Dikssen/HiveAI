import { useState, useEffect } from "react";
import { api } from "../api/client";

const AGENT_ICONS = {
  ChiefOrchestratorAgent: "🧠",
  BackendDeveloperAgent:  "💻",
  QAEngineerAgent:        "🧪",
  DevOpsAgent:            "🚀",
  DataAnalystAgent:       "📊",
  BusinessAnalystAgent:   "📋",
  ProjectManagerAgent:    "📌",
  SupportEngineerAgent:   "🎧",
};

const AGENT_COLORS = {
  ChiefOrchestratorAgent: "#6366f1",
  BackendDeveloperAgent:  "#3b82f6",
  QAEngineerAgent:        "#10b981",
  DevOpsAgent:            "#f59e0b",
  DataAnalystAgent:       "#8b5cf6",
  BusinessAnalystAgent:   "#ec4899",
  ProjectManagerAgent:    "#06b6d4",
  SupportEngineerAgent:   "#64748b",
};

function duration(run) {
  if (!run.started_at || !run.finished_at) return null;
  const ms = new Date(run.finished_at) - new Date(run.started_at);
  return `${(ms / 1000).toFixed(1)}s`;
}

function TextBlock({ label, text, accent = "#6366f1", defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  if (!text) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <div
        onClick={() => setOpen(v => !v)}
        style={{
          cursor: "pointer", fontSize: 12, fontWeight: 600,
          color: accent, userSelect: "none", display: "flex", alignItems: "center", gap: 4,
        }}
      >
        <span>{open ? "▼" : "▶"}</span> {label}
        <span style={{ fontWeight: 400, color: "#9ca3af", fontSize: 11 }}>
          ({text.length} chars)
        </span>
      </div>
      {open && (
        <pre style={{
          marginTop: 6, padding: "10px 14px",
          background: "#f8fafc", border: `1px solid ${accent}30`,
          borderLeft: `3px solid ${accent}`,
          borderRadius: 6, fontSize: 12, lineHeight: 1.6,
          whiteSpace: "pre-wrap", wordBreak: "break-word",
          maxHeight: 400, overflowY: "auto",
        }}>
          {text}
        </pre>
      )}
    </div>
  );
}

function EvalBlock({ ev }) {
  if (!ev) return null;
  const ok = ev.is_complete;
  return (
    <div style={{
      margin: "0 0 0 48px",
      padding: "8px 14px",
      background: ok ? "#f0fdf4" : "#fffbeb",
      border: `1px solid ${ok ? "#86efac" : "#fde68a"}`,
      borderRadius: 8,
      fontSize: 12,
    }}>
      <div style={{ fontWeight: 700, color: ok ? "#15803d" : "#92400e", marginBottom: 2 }}>
        {ok ? "✓ Evaluation: Complete" : `↻ Evaluation: Not done — next: ${ev.next_agent || "?"}`}
      </div>
      {ev.reason && <div style={{ color: "#374151" }}>{ev.reason}</div>}
      {!ok && ev.next_task?.description && (
        <div style={{ marginTop: 6, color: "#374151", borderTop: "1px solid #fde68a", paddingTop: 6 }}>
          <span style={{ fontWeight: 600 }}>Next task: </span>
          {ev.next_task.description}
        </div>
      )}
    </div>
  );
}

function AgentStep({ run, index, evaluation, isLast }) {
  const color = AGENT_COLORS[run.agent_name] || "#64748b";
  const icon  = AGENT_ICONS[run.agent_name]  || "🤖";
  const dur   = duration(run);
  const isOrchestrator = run.agent_name === "ChiefOrchestratorAgent";
  const iteration = run.input_payload?.iteration;

  // full task text (includes prior context injected by orchestrator)
  const fullTask = run.input_payload?.description || run.task_description || "";
  // split prior context from actual task if both present
  const ctxMatch = fullTask.match(/## Context from previous work\n\n([\s\S]*?)\n\n## Your task\n\n([\s\S]*)/);
  const priorCtx  = ctxMatch ? ctxMatch[1] : null;
  const actualTask = ctxMatch ? ctxMatch[2] : fullTask;

  const output = run.output_payload?.result || run.output_payload?.final_answer_preview || "";

  return (
    <div style={{ marginBottom: isLast ? 0 : 4 }}>
      {/* Step row */}
      <div style={{ display: "flex", gap: 12 }}>
        {/* Icon + spine */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
          <div style={{
            width: 40, height: 40, borderRadius: "50%",
            background: color + "18", border: `2.5px solid ${color}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 18, flexShrink: 0,
          }}>
            {icon}
          </div>
          {(!isLast || evaluation) && (
            <div style={{ width: 2, flex: 1, background: "#e2e8f0", minHeight: 20 }} />
          )}
        </div>

        {/* Card */}
        <div style={{
          flex: 1,
          background: "#fff",
          border: `1px solid ${color}30`,
          borderLeft: `4px solid ${color}`,
          borderRadius: 10,
          padding: "12px 16px",
          marginBottom: 8,
        }}>
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontWeight: 800, fontSize: 15, color }}>
              {run.agent_name.replace("Agent", "")}
            </span>
            {iteration != null && !isOrchestrator && (
              <span style={{
                fontSize: 11, padding: "2px 8px", borderRadius: 12,
                background: color + "18", color, fontWeight: 700,
              }}>
                iteration {iteration}
              </span>
            )}
            <span style={{
              fontSize: 11, padding: "2px 8px", borderRadius: 12,
              background: run.status === "completed" ? "#d1fae5" : run.status === "failed" ? "#fee2e2" : "#f1f5f9",
              color: run.status === "completed" ? "#065f46" : run.status === "failed" ? "#991b1b" : "#475569",
              fontWeight: 600,
            }}>
              {run.status}
            </span>
            {dur && <span style={{ fontSize: 12, color: "#9ca3af" }}>⏱ {dur}</span>}
          </div>

          {/* Orchestrator: plan */}
          {isOrchestrator && run.output_payload?.reasoning && (
            <TextBlock
              label="Plan (reasoning)"
              text={run.output_payload.reasoning}
              accent="#6366f1"
              defaultOpen
            />
          )}
          {isOrchestrator && run.output_payload?.agents_used && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#374151" }}>
              <span style={{ fontWeight: 600, color: "#6366f1" }}>Selected agents: </span>
              {[...new Set(run.output_payload.agents_used)].join(" → ")}
            </div>
          )}

          {/* Agent: what was passed to it */}
          {!isOrchestrator && (
            <>
              {priorCtx && (
                <TextBlock label="Context received from previous agents" text={priorCtx} accent="#94a3b8" />
              )}
              <TextBlock label="Task received from orchestrator" text={actualTask} accent={color} defaultOpen />
            </>
          )}

          {/* Output */}
          {output && (
            <TextBlock
              label={isOrchestrator ? "Final synthesized answer" : "Agent output"}
              text={output}
              accent={color}
              defaultOpen={!isOrchestrator}
            />
          )}

          {/* Error */}
          {run.error && (
            <div style={{
              marginTop: 8, padding: "8px 12px",
              background: "#fef2f2", border: "1px solid #fca5a5",
              borderRadius: 6, fontSize: 12, color: "#dc2626",
            }}>
              ❌ {run.error}
            </div>
          )}
        </div>
      </div>

      {/* Evaluation connector */}
      {evaluation && (
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ width: 40, flexShrink: 0, display: "flex", justifyContent: "center" }}>
            <div style={{ width: 2, background: "#e2e8f0", minHeight: 16 }} />
          </div>
          <div style={{ flex: 1, paddingBottom: 8 }}>
            <EvalBlock ev={evaluation} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function RunDetailPage({ orchestratorRunId, chatId, onBack }) {
  const [runs, setRuns]     = useState([]);
  const [evalLogs, setEvalLogs] = useState([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const allRuns = await api.getAgentRuns(chatId);

        // Find this orchestration session: orchestrator run + all runs until next orchestrator
        const orchIdx = allRuns.findIndex(r => r.id === orchestratorRunId);
        if (orchIdx === -1) { setLoading(false); return; }

        const sessionRuns = [allRuns[orchIdx]];
        for (let i = orchIdx + 1; i < allRuns.length; i++) {
          if (allRuns[i].agent_name === "ChiefOrchestratorAgent") break;
          sessionRuns.push(allRuns[i]);
        }
        setRuns(sessionRuns);

        // Load evaluation logs from orchestrator
        const logs = await api.getAgentRunLogs(orchestratorRunId);
        const evals = logs
          .filter(l => l.message === "Evaluation result")
          .map(l => l.metadata_ || {});
        setEvalLogs(evals);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [orchestratorRunId, chatId]);

  const orchestratorRun = runs[0];
  const agentRuns = runs.slice(1);
  // Orchestrator goes last (final synthesis), so full order is: orch header → agents → orch tail
  // We show: orch (plan only) → agents with evals → final answer from orch output

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden", background: "#f8fafc" }}>
      {/* Header */}
      <div style={{
        padding: "12px 20px", background: "#fff",
        borderBottom: "1px solid #e5e7eb",
        display: "flex", alignItems: "center", gap: 12, flexShrink: 0,
      }}>
        <button
          onClick={onBack}
          style={{
            background: "none", border: "1px solid #e5e7eb",
            borderRadius: 6, padding: "4px 12px",
            cursor: "pointer", fontSize: 13, color: "#374151",
          }}
        >
          ← Back
        </button>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: "#111827" }}>
            Run #{orchestratorRunId} — Full Agent Flow
          </div>
          <div style={{ fontSize: 12, color: "#6b7280" }}>
            {orchestratorRun?.task_description || ""}
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px" }}>
        {loading && (
          <div style={{ color: "#9ca3af", fontSize: 14, textAlign: "center", paddingTop: 40 }}>
            Loading run details…
          </div>
        )}

        {!loading && orchestratorRun && (
          <>
            {/* Orchestrator plan */}
            <AgentStep
              run={{ ...orchestratorRun, output_payload: { reasoning: orchestratorRun.output_payload?.reasoning, agents_used: orchestratorRun.output_payload?.agents_used } }}
              index={0}
              evaluation={null}
              isLast={agentRuns.length === 0}
            />

            {/* Agent steps with evaluations */}
            {agentRuns.map((run, idx) => {
              const isLast = idx === agentRuns.length - 1;
              const ev = evalLogs[idx] || null;
              return (
                <AgentStep
                  key={run.id}
                  run={run}
                  index={idx + 1}
                  evaluation={isLast && ev?.is_complete ? ev : (!isLast ? ev : null)}
                  isLast={isLast && !orchestratorRun.output_payload?.final_answer_preview}
                />
              );
            })}

            {/* Final answer from orchestrator */}
            {orchestratorRun.output_payload?.final_answer_preview && (
              <div style={{ display: "flex", gap: 12 }}>
                <div style={{ width: 40, flexShrink: 0, display: "flex", justifyContent: "center" }}>
                  <div style={{ width: 2, background: "#e2e8f0", height: 20 }} />
                </div>
                <div style={{ flex: 1, marginBottom: 8 }}>
                  <div style={{
                    background: "#fff",
                    border: "1px solid #6366f130",
                    borderLeft: "4px solid #6366f1",
                    borderRadius: 10,
                    padding: "12px 16px",
                  }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "#6366f1", marginBottom: 8 }}>
                      🎯 Final Answer (synthesized)
                    </div>
                    <pre style={{
                      fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word",
                      lineHeight: 1.6, color: "#111827",
                    }}>
                      {orchestratorRun.output_payload.final_answer_preview}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
