import { useState, useEffect } from "react";
import { api } from "../api/client";
import StatusBadge from "./StatusBadge";

function AgentCard({ run, expanded, onToggle }) {
  const [logs, setLogs] = useState(null);

  const loadLogs = async () => {
    if (logs !== null) { onToggle(); return; }
    try {
      const data = await api.getAgentRunLogs(run.id);
      setLogs(data);
    } catch {
      setLogs([]);
    }
    onToggle();
  };

  const output = run.output_payload?.result || run.output_payload?.final_answer_preview || "";
  const durationMs =
    run.started_at && run.finished_at
      ? new Date(run.finished_at) - new Date(run.started_at)
      : null;

  return (
    <div style={{ borderLeft: "3px solid #3b82f6", paddingLeft: 12, marginBottom: 12 }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
        onClick={loadLogs}
      >
        <span style={{ fontWeight: 600, fontSize: 13 }}>{run.agent_name}</span>
        <StatusBadge status={run.status} />
        {durationMs !== null && (
          <span style={{ fontSize: 11, color: "#9ca3af" }}>
            {(durationMs / 1000).toFixed(1)}s
          </span>
        )}
        <span style={{ fontSize: 11, color: "#6b7280", marginLeft: "auto" }}>
          {expanded ? "▲ hide" : "▼ details"}
        </span>
      </div>

      {run.task_description && (
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
          {run.task_description}
        </div>
      )}

      {expanded && (
        <div style={{ marginTop: 8 }}>
          {run.error && (
            <div
              style={{
                background: "#fef2f2",
                border: "1px solid #fca5a5",
                borderRadius: 4,
                padding: 8,
                fontSize: 12,
                color: "#dc2626",
                marginBottom: 6,
              }}
            >
              <strong>Error:</strong> {run.error}
            </div>
          )}

          {output && (
            <div
              style={{
                background: "#f9fafb",
                border: "1px solid #e5e7eb",
                borderRadius: 4,
                padding: 8,
                fontSize: 12,
                whiteSpace: "pre-wrap",
                maxHeight: 300,
                overflowY: "auto",
              }}
            >
              <strong>Output:</strong>
              <br />
              {output}
            </div>
          )}

          {logs !== null && logs.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#6b7280", marginBottom: 4 }}>
                LOGS
              </div>
              {logs.map((log) => (
                <div
                  key={log.id}
                  style={{
                    fontSize: 11,
                    color: log.level === "ERROR" ? "#dc2626" : log.level === "WARNING" ? "#d97706" : "#374151",
                    borderBottom: "1px solid #f3f4f6",
                    paddingBottom: 2,
                    marginBottom: 2,
                  }}
                >
                  <span style={{ color: "#9ca3af" }}>{log.level}</span>{" "}
                  {log.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AgentRunTimeline({ chatId, refreshKey }) {
  const [runs, setRuns] = useState([]);
  const [expandedIds, setExpandedIds] = useState(new Set());

  useEffect(() => {
    if (!chatId) return;
    api.getAgentRuns(chatId).then(setRuns).catch(() => {});
  }, [chatId, refreshKey]);

  if (!runs.length) return null;

  const toggle = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  return (
    <div
      style={{
        borderTop: "1px solid #e5e7eb",
        padding: "12px 16px",
        background: "#fafafa",
      }}
    >
      <div style={{ fontSize: 12, fontWeight: 700, color: "#6b7280", marginBottom: 10 }}>
        AGENT EXECUTION TIMELINE
      </div>
      {runs.map((run) => (
        <AgentCard
          key={run.id}
          run={run}
          expanded={expandedIds.has(run.id)}
          onToggle={() => toggle(run.id)}
        />
      ))}
    </div>
  );
}
