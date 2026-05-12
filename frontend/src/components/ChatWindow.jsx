import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api/client";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import AgentRunTimeline from "./AgentRunTimeline";
import StatusBadge from "./StatusBadge";

export default function ChatWindow({ chatId, onViewRun }) {
  const [messages, setMessages] = useState([]);
  const [resumeTaskId, setResumeTaskId] = useState(null);
  const [timelineKey, setTimelineKey] = useState(0);
  const [showTimeline, setShowTimeline] = useState(true);
  const [agentRuns, setAgentRuns] = useState([]);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const loadMessages = useCallback(async () => {
    if (!chatId) return;
    try {
      const data = await api.getMessages(chatId);
      setMessages(data);
    } catch (e) {
      setError(e.message);
    }
  }, [chatId]);

  // Polling fallback — kicks in when the user returns to a chat mid-processing
  useEffect(() => {
    if (!resumeTaskId) {
      clearInterval(pollRef.current);
      return;
    }
    const poll = async () => {
      try {
        const task = await api.getTask(resumeTaskId);
        if (task.status === "completed" || task.status === "failed") {
          clearInterval(pollRef.current);
          setResumeTaskId(null);
          await loadMessages();
          setTimelineKey((k) => k + 1);
          api.getAgentRuns(chatId).then(setAgentRuns).catch(() => {});
        }
      } catch {}
    };
    poll();
    pollRef.current = setInterval(poll, 2500);
    return () => clearInterval(pollRef.current);
  }, [resumeTaskId, loadMessages, chatId]);

  // On chat switch: check for in-progress tasks to resume via polling
  useEffect(() => {
    clearInterval(pollRef.current);
    setMessages([]);
    setResumeTaskId(null);
    setError(null);
    setAgentRuns([]);

    if (!chatId) return;

    loadMessages();
    // Check for an active task first — more reliable than scanning agent runs
    api.getActiveTask(chatId).then((active) => {
      if (active?.task_id) setResumeTaskId(active.task_id);
    });
    api.getAgentRuns(chatId).then(setAgentRuns).catch(() => {});

    return () => clearInterval(pollRef.current);
  }, [chatId]);

  const handleSend = async (content) => {
    clearInterval(pollRef.current);
    setError(null);
    setResumeTaskId(null);

    const tempMsg = {
      id: Date.now(),
      chat_id: chatId,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempMsg]);

    try {
      const { task_id } = await api.sendMessage(chatId, content);
      setResumeTaskId(task_id);
    } catch (e) {
      setError(e.message);
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id));
    }
  };

  const isProcessing = !!resumeTaskId;

  if (!chatId) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#9ca3af",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div style={{ fontSize: 48 }}>🤖</div>
        <div style={{ fontSize: 16 }}>Виберіть або створіть чат</div>
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        overflow: "hidden",
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          padding: "10px 16px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          gap: 12,
          background: "#fff",
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 14, color: "#111827" }}>
          Chat #{chatId}
        </span>
        {isProcessing && <StatusBadge status="running" />}

        {(() => {
          const lastOrch = [...agentRuns].reverse().find(r => r.agent_name === "ChiefOrchestratorAgent");
          return lastOrch ? (
            <button
              onClick={() => onViewRun(lastOrch.id)}
              style={{
                marginLeft: "auto",
                padding: "4px 14px",
                fontSize: 12,
                background: "#6366f1",
                border: "none",
                borderRadius: 6,
                cursor: "pointer",
                color: "#fff",
                fontWeight: 600,
              }}
            >
              🔍 View agent flow
            </button>
          ) : <span style={{ marginLeft: "auto" }} />;
        })()}

        <button
          onClick={() => setShowTimeline((v) => !v)}
          style={{
            padding: "4px 12px",
            fontSize: 12,
            background: showTimeline ? "#eff6ff" : "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: 6,
            cursor: "pointer",
            color: "#374151",
          }}
        >
          {showTimeline ? "▼ Hide" : "▲ Show"} Timeline
        </button>
      </div>

      {error && (
        <div
          style={{
            background: "#fef2f2",
            color: "#dc2626",
            padding: "8px 16px",
            fontSize: 13,
            borderBottom: "1px solid #fca5a5",
            flexShrink: 0,
          }}
        >
          ⚠️ {error}
        </div>
      )}

      <MessageList
        messages={messages}
        isProcessing={isProcessing}
      />

      {showTimeline && (
        <div style={{ flexShrink: 0, maxHeight: "35vh", overflowY: "auto" }}>
          <AgentRunTimeline chatId={chatId} refreshKey={timelineKey} onViewRun={onViewRun} />
        </div>
      )}

      <div style={{ flexShrink: 0 }}>
        <MessageInput onSend={handleSend} disabled={isProcessing} />
      </div>
    </div>
  );
}
