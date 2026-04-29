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

// ── Small collapsible text block ────────────────────────────────────────────
function Collapsible({ label, text, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  if (!text) return null;
  return (
    <div style={{ marginTop: 6 }}>
      <div
        onClick={() => setOpen((v) => !v)}
        style={{ cursor: "pointer", fontSize: 11, color: "#6b7280", userSelect: "none" }}
      >
        {open ? "▲" : "▼"} {label}
      </div>
      {open && (
        <pre
          style={{
            marginTop: 4,
            padding: "8px 10px",
            background: "#f8fafc",
            border: "1px solid #e2e8f0",
            borderRadius: 6,
            fontSize: 11,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: 300,
            overflowY: "auto",
          }}
        >
          {text}
        </pre>
      )}
    </div>
  );
}

// ── Evaluation connector between two agent cards ─────────────────────────────
function EvaluationConnector({ eval: ev }) {
  if (!ev) return <div style={{ width: 2, height: 12, background: "#e2e8f0", margin: "0 auto 0 19px" }} />;

  const complete = ev.is_complete;
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 8, margin: "4px 0", paddingLeft: 8 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        <div style={{ width: 2, height: 8, background: "#e2e8f0" }} />
        <div
          style={{
            width: 24,
            height: 24,
            borderRadius: "50%",
            background: complete ? "#d1fae5" : "#fef9c3",
            border: `2px solid ${complete ? "#10b981" : "#eab308"}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            flexShrink: 0,
          }}
        >
          {complete ? "✓" : "↻"}
        </div>
        <div style={{ width: 2, height: 8, background: "#e2e8f0" }} />
      </div>
      <div style={{ paddingTop: 4 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: complete ? "#059669" : "#92400e" }}>
          {complete ? "Evaluation: complete" : `Evaluation: retry → ${ev.next_agent || "?"}`}
        </div>
        {ev.reason && (
          <div style={{ fontSize: 11, color: "#6b7280", marginTop: 1 }}>{ev.reason}</div>
        )}
      </div>
    </div>
  );
}

// ── Single agent card ────────────────────────────────────────────────────────
function AgentCard({ run, iteration }) {
  const [open, setOpen] = useState(false);
  const icon  = AGENT_ICONS[run.agent_name]  || "🤖";
  const color = AGENT_COLORS[run.agent_name] || "#64748b";
  const dur   = duration(run);
  const output = run.output_payload?.result || run.output_payload?.final_answer_preview || "";
  const task   = run.task_description || "";
  const isOrchestrator = run.agent_name === "ChiefOrchestratorAgent";

  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 4 }}>
      {/* Timeline spine + icon */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: color + "20",
            border: `2px solid ${color}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 15,
          }}
        >
          {icon}
        </div>
      </div>

      {/* Card body */}
      <div
        style={{
          flex: 1,
          background: "#fff",
          border: `1px solid ${color}40`,
          borderLeft: `3px solid ${color}`,
          borderRadius: 8,
          padding: "8px 12px",
          marginBottom: 2,
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span style={{ fontWeight: 700, fontSize: 13, color }}>
            {run.agent_name.replace("Agent", "")}
          </span>
          {iteration != null && !isOrchestrator && (
            <span
              style={{
                fontSize: 10,
                background: color + "20",
                color,
                borderRadius: 4,
                padding: "1px 6px",
                fontWeight: 600,
              }}
            >
              iter {iteration}
            </span>
          )}
          <span
            style={{
              fontSize: 10,
              borderRadius: 4,
              padding: "1px 6px",
              background:
                run.status === "completed" ? "#d1fae5" :
                run.status === "running"   ? "#fef9c3" :
                run.status === "failed"    ? "#fee2e2" : "#f1f5f9",
              color:
                run.status === "completed" ? "#065f46" :
                run.status === "running"   ? "#92400e" :
                run.status === "failed"    ? "#991b1b" : "#475569",
            }}
          >
            {run.status}
          </span>
          {dur && <span style={{ fontSize: 11, color: "#9ca3af" }}>{dur}</span>}
          <span
            onClick={() => setOpen((v) => !v)}
            style={{ marginLeft: "auto", fontSize: 11, color: "#9ca3af", cursor: "pointer" }}
          >
            {open ? "▲ hide" : "▼ details"}
          </span>
        </div>

        {/* Task (always visible, truncated) */}
        {task && !isOrchestrator && (
          <div
            style={{
              marginTop: 4,
              fontSize: 11,
              color: "#374151",
              background: "#f8fafc",
              borderRadius: 4,
              padding: "4px 8px",
              borderLeft: "2px solid #cbd5e1",
            }}
          >
            <span style={{ fontWeight: 600, color: "#64748b" }}>Task: </span>
            {task.length > 200 ? task.slice(0, 200) + "…" : task}
          </div>
        )}

        {/* Orchestrator: show reasoning */}
        {isOrchestrator && run.output_payload?.reasoning && (
          <div
            style={{
              marginTop: 4,
              fontSize: 11,
              color: "#374151",
              background: "#f8fafc",
              borderRadius: 4,
              padding: "4px 8px",
              borderLeft: "2px solid #a5b4fc",
            }}
          >
            <span style={{ fontWeight: 600, color: "#6366f1" }}>Plan: </span>
            {run.output_payload.reasoning.slice(0, 300)}
            {run.output_payload.reasoning.length > 300 ? "…" : ""}
          </div>
        )}

        {/* Expanded: full task + output */}
        {open && (
          <>
            {task.length > 200 && (
              <Collapsible label="Full task" text={task} defaultOpen />
            )}
            <Collapsible label={`Output (${output.length} chars)`} text={output} defaultOpen={!!output} />
            {run.error && (
              <div style={{ marginTop: 6, fontSize: 11, color: "#dc2626", background: "#fef2f2", borderRadius: 4, padding: "4px 8px" }}>
                ❌ {run.error}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Session: one orchestration round (one user message) ─────────────────────
function Session({ orchestratorRun, agentRuns, onViewRun }) {
  const [evalLogs, setEvalLogs] = useState(null);

  useEffect(() => {
    api.getAgentRunLogs(orchestratorRun.id)
      .then((logs) => {
        const evals = logs
          .filter((l) => l.message === "Evaluation result")
          .map((l) => l.metadata_ || {});
        setEvalLogs(evals);
      })
      .catch(() => setEvalLogs([]));
  }, [orchestratorRun.id]);

  // Sort agent runs by created_at, skip the orchestrator itself
  const sorted = [...agentRuns].sort(
    (a, b) => new Date(a.created_at) - new Date(b.created_at)
  );

  return (
    <div style={{ marginBottom: 24 }}>
      {/* Orchestrator planning card */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <div style={{ flex: 1 }}>
          <AgentCard run={orchestratorRun} />
        </div>
        <button
          onClick={() => onViewRun(orchestratorRun.id)}
          title="View full run details"
          style={{
            marginTop: 4, flexShrink: 0,
            background: "#eff6ff", border: "1px solid #bfdbfe",
            borderRadius: 6, padding: "4px 10px",
            cursor: "pointer", fontSize: 11, color: "#1d4ed8", whiteSpace: "nowrap",
          }}
        >
          Full run →
        </button>
      </div>

      {/* Connector from orchestrator to first agent */}
      {sorted.length > 0 && (
        <div style={{ width: 2, height: 10, background: "#e2e8f0", margin: "0 0 0 19px" }} />
      )}

      {/* Agent runs interleaved with evaluations */}
      {sorted.map((run, idx) => {
        const iteration = run.input_payload?.iteration ?? null;
        const ev = evalLogs ? evalLogs[idx] : null;
        const isLast = idx === sorted.length - 1;

        return (
          <div key={run.id}>
            <AgentCard run={run} iteration={iteration} />
            {!isLast && <EvaluationConnector eval={ev} />}
            {isLast && ev && <EvaluationConnector eval={ev} />}
          </div>
        );
      })}
    </div>
  );
}

// ── Root component ────────────────────────────────────────────────────────────
export default function AgentRunTimeline({ chatId, refreshKey, onViewRun }) {
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    if (!chatId) return;
    api.getAgentRuns(chatId).then(setRuns).catch(() => {});
  }, [chatId, refreshKey]);

  if (!runs.length) return null;

  const sessions = [];
  let current = null;
  for (const run of runs) {
    if (run.agent_name === "ChiefOrchestratorAgent") {
      current = { orchestratorRun: run, agentRuns: [] };
      sessions.push(current);
    } else if (current) {
      current.agentRuns.push(run);
    }
  }

  return (
    <div style={{ padding: "12px 16px", background: "#f8fafc" }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: "#6b7280", marginBottom: 12, letterSpacing: 1 }}>
        AGENT FLOW
      </div>
      {sessions.map((s) => (
        <Session
          key={s.orchestratorRun.id}
          orchestratorRun={s.orchestratorRun}
          agentRuns={s.agentRuns}
          onViewRun={onViewRun}
        />
      ))}
    </div>
  );
}
