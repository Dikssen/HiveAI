import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api/client";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import AgentRunTimeline from "./AgentRunTimeline";
import StatusBadge from "./StatusBadge";

export default function ChatWindow({ chatId }) {
  const [messages, setMessages] = useState([]);
  const [pendingTaskId, setPendingTaskId] = useState(null);
  const [taskStatus, setTaskStatus] = useState(null);
  const [timelineKey, setTimelineKey] = useState(0);
  const [showTimeline, setShowTimeline] = useState(true);
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

  useEffect(() => {
    setMessages([]);
    setPendingTaskId(null);
    setTaskStatus(null);
    setError(null);
    if (chatId) loadMessages();
  }, [chatId]);

  useEffect(() => {
    if (!pendingTaskId) {
      clearInterval(pollRef.current);
      return;
    }
    const poll = async () => {
      try {
        const task = await api.getTask(pendingTaskId);
        setTaskStatus(task.status);
        setTimelineKey((k) => k + 1);
        if (task.status === "completed" || task.status === "failed") {
          clearInterval(pollRef.current);
          setPendingTaskId(null);
          await loadMessages();
          setTimelineKey((k) => k + 1);
        }
      } catch {
        // backend restarting — keep polling
      }
    };
    poll();
    pollRef.current = setInterval(poll, 2500);
    return () => clearInterval(pollRef.current);
  }, [pendingTaskId, loadMessages]);

  const handleSend = async (content) => {
    setError(null);
    const tempMsg = {
      id: Date.now(),
      chat_id: chatId,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempMsg]);
    try {
      const result = await api.sendMessage(chatId, content);
      setPendingTaskId(result.task_id);
      setTaskStatus("pending");
      await loadMessages();
    } catch (e) {
      setError(e.message);
      setMessages((prev) => prev.filter((m) => m.id !== tempMsg.id));
    }
  };

  const isProcessing = taskStatus === "pending" || taskStatus === "running";

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
    // Outer wrapper: takes all remaining height from App, nothing overflows out
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minHeight: 0, // ← дозволяє flex-дітям мати scroll замість розтягування
        overflow: "hidden",
      }}
    >
      {/* Toolbar — фіксована висота */}
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
        {taskStatus && <StatusBadge status={taskStatus} />}
        <button
          onClick={() => setShowTimeline((v) => !v)}
          style={{
            marginLeft: "auto",
            padding: "4px 12px",
            fontSize: 12,
            background: showTimeline ? "#eff6ff" : "#f9fafb",
            border: "1px solid #e5e7eb",
            borderRadius: 6,
            cursor: "pointer",
            color: "#374151",
          }}
        >
          {showTimeline ? "▼ Hide" : "▲ Show"} Agent Timeline
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

      {/* Messages — займає весь вільний простір, прокручується */}
      <MessageList messages={messages} isProcessing={isProcessing} />

      {/* Agent timeline — фіксована знизу, власний скрол якщо потрібно */}
      {showTimeline && (
        <div style={{ flexShrink: 0, maxHeight: "35vh", overflowY: "auto" }}>
          <AgentRunTimeline chatId={chatId} refreshKey={timelineKey} />
        </div>
      )}

      {/* Input — фіксована знизу */}
      <div style={{ flexShrink: 0 }}>
        <MessageInput onSend={handleSend} disabled={isProcessing} />
      </div>
    </div>
  );
}
